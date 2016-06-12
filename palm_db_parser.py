#!/usr/bin/python

from bitstring import ConstBitArray
import datetime

class ToDoRecord:

	def __init__(self, raw_record):
		record = ConstBitArray(bytes=raw_record[0:3])

		self.due_year = record[0:7].uint + 1904 # Mac date
		self.due_month = record[8:11].uint
		self.due_day = record[12:16].uint
		if record[0:8] == '0b11111111':
			self.due_date = "" # due date not set
		else:
			self.due_date = "%s.%s. %s " % (self.due_day, self.due_month, self.due_year)
		self.done = record[16]
		self.priority = record[21:24].uint
		self.description, self.note = raw_record[3:-1].split('\0') # both may contain \n characters

	def __str__(self):
		return "%s[%s] P%s: %s (%s)" % (self.due_date, self.done, self.priority, self.description, self.note)

class MemoRecord:

	def __init__(self, raw_record):
		self.text, ignored = raw_record.split('\0')

	def __str__(self):
		return self.text

class AddressBookRecord:

	def __init__(self, raw_record, field_names=None):
		custom_fields = ConstBitArray(bytes=raw_record[0:4]) # only 6 least significant 4bit nibbles are used
		fields_used = ConstBitArray(bytes=raw_record[4:8]) # bitfield - indicates if field_name is present in field_values
		field_values = raw_record[9:-1].split('\0') # null-terminated strings for each used filed (+get rid of leading and trailing \0)

		if not field_names: # use default names for record fields
			field_names = { 0:"Last Name", 1:"First Name", 2:"Company", 3:"Phone1",
							4:"Phone2", 5:"Phone3", 6:"Phone4", 7:"Phone5",
							8:"Address", 9:"City", 10:"State", 11:"Zip Code",
							12:"Country", 13:"Title", 14:"Custom1", 15:"Custom2",
							16:"Custom3", 17:"Custom4", 18:"Note", 19:"Phone6",
							20:"Phone7", 21:"Phone8" }

		fields = field_names # make a copy for per-record field renaming
		renames = ( "Work", "Home","Fax", "Other", "E-mail", "Main", "Pager", "Mobile" ) # phones 1-5 may be renamed to these fields
		fields[3] = renames[ custom_fields[28:32].uint ] # renamed Phone1
		fields[4] = renames[ custom_fields[24:28].uint ] # renamed Phone2
		fields[5] = renames[ custom_fields[20:24].uint ] # renamed Phone3
		fields[6] = renames[ custom_fields[16:20].uint ] # renamed Phone4
		fields[7] = renames[ custom_fields[12:16].uint ] # renamed Phone5

		self.fields = {}
		field_num = 0
		for bit in range(31, 10, -1): # start from LSB and go through all 22 fields
			if fields_used[bit]: # skip unused fields
				self.fields[ fields[31 - bit] ] = field_values[field_num] # respect field renaming
				field_num += 1

		self.default_field = fields[ 3 + custom_fields[8:12].uint ] # is displayed in list view, always contains one of renames
		if self.default_field not in self.fields: # fix for records with no phone and default field set to 0 (Work)
			self.default_field = ""

	def __str__(self):
		return self.fields.__str__() + " Default: " + self.default_field

class DateBookRecord:
	def __init__(self, raw_record):

		# event starts occuring since date
		raw_date = ConstBitArray(bytes=raw_record[4:6])
		self.day = raw_date[11:16].uint
		self.month = raw_date[7:11].uint
		self.year = raw_date[0:7].uint + 1904 # Mac date
		self.occurs = "%s.%s %s " % (self.day, self.month, self.year)

		# event occurs between start and end time
		self.time = {}
		start_hour = ConstBitArray(bytes=raw_record[0]).uintbe
		if start_hour != 0xFF: # event occurs on particular time
			self.time["start_hour"] = start_hour
			self.time["start_minute"] = ConstBitArray(bytes=raw_record[1]).uintbe
			self.time["end_hour"] = ConstBitArray(bytes=raw_record[2]).uintbe
			self.time["end_minute"] = ConstBitArray(bytes=raw_record[3]).uintbe
			self.occurs += "%02d:%02d-%02d:%02d" % (self.time["start_hour"], self.time["start_minute"], self.time["end_hour"], self.time["end_minute"])
		else:
			self.occurs += "allday"

		# event flags
		raw_flags = ConstBitArray(bytes=raw_record[6:8]) # bits [0] and [7:] are ignored, has_location is stored in [6] but currently ignored (location follows after note + has timezone info after itself)

		offset = 8 # alarm, repeat and exceptions may further shift it

		# event with alarm
		self.alarm = {}
		if raw_flags[1]: # has alarm
			self.alarm["advance"] = raw_record[offset] # how many units in advance the alarm rings
			unit_type = ConstBitArray(bytes=raw_record[offset + 1]).uintbe
			unit_types = { 0: "minutes", 1: "hours", 2: "days" }
			self.alarm["unit"] = unit_types[unit_type]
			offset += 2

		# repeating event
		self.repeat = {}
		self.repeat_until = ""
		self.repeat_type = ""
		if raw_flags[2]: # is repeating
			repeat_types = { 1: "daily", 2: "weekly", 3: "monthly by day", 4: "monthly by date", 5: "yearly" }
			repeat_type = ConstBitArray(bytes=raw_record[offset]).uintbe
			self.repeat["type"] = repeat_types[repeat_type]
			self.repeat_type = " repeat " + repeat_types[repeat_type]

			# end of repeating
			raw_end_date = ConstBitArray(bytes=raw_record[offset + 2:offset + 4]) # [offset + 1] is always \0
			if raw_end_date != "0xFFFF": # repeat has end date
				self.repeat["end"] = {}
				self.repeat["end"]["day"] = raw_end_date[11:16].uint
				self.repeat["end"]["month"] = raw_end_date[7:11].uint
				self.repeat["end"]["year"] = raw_end_date[0:7].uint + 1904 # Mac date
				self.repeat_until = " until %s.%s %s" % (self.repeat["end"]["day"], self.repeat["end"]["month"], self.repeat["end"]["year"])
			else:
				self.repeat["end"] = None
				self.repeat_until = " forever"

			# repeat every X
			repeat_on = ConstBitArray(bytes=raw_record[offset + 5])
			repeat_frequency = raw_record[offset + 4]
			start_of_week = raw_record[offset + 6] # [offset + 7] is unused
			# TODO: check if start of week doesn't shift the keys
			# repeat_days = { 7: "Mon", 6: "Tue", 5: "Wed", 4: "Thu", 3: "Fri", 2: "Sat", 1: "Sun" }
			repeat_days = { 7: "Sun", 6: "Mon", 5: "Tue", 4: "Wed", 3: "Thu", 2: "Fri", 1: "Sat" }

			if repeat_type == "weekly": # e.g. every Mon, Tue and Fri
				self.repeat["days"] = []
				for day in repeat_days.keys():
					if repeat_on[day]:
						self.repeat["days"].append( repeat_days[day] ) # FIXME - is ignored
				self.repeat_type += " " + str(self.repeat["days"])

			if repeat_type == "monthly by day": # e.g. every 2nd Fri
				if repeat_on == 5:
					self.repeat["week"] = "last"
				else:
					self.repeat["week"] = repeat_on[5:8].uint + 1 # every Xth weekday of month
				self.repeat["day"] = repeat_days[ repeat_on[0:5] ] # weekday
				self.repeat_type += " " + self.repeat["day"] + " " + self.repeat["week"] # FIXME - is ignored

			offset += 8

		# event occurance exceptions
		self.exceptions = []
		if raw_flags[4]: # has exceptions
			num_exceptions = ConstBitArray(bytes=raw_record[offset:offset + 2]).uintbe
			offset += 2
			for exception in range(num_exceptions):
				raw_exception = ConstBitArray(bytes=raw_record[offset: offset + 2])
				day = raw_exception[11:16].uint
				month = raw_exception[7:11].uint
				year = raw_exception[0:7].uint + 1904 # Mac date
				self.exceptions.append( (day, month, year) ) # exceptions are list of tuples
				offset += 2

		# event description
		if raw_flags[5]: # has description
			self.text, ignore, raw_note = raw_record[offset:].partition('\0')
		else:
			self.note = "" # casem None

		# event note
		if raw_flags[3]: # has note
			self.note, ignore1, ignore2 = raw_note.partition('\0')
		else:
			self.note = "" # casem None

	def __str__(self):
		return self.occurs + self.repeat_type + self.repeat_until + ": " + self.text + " (" + self.note + ") "

class PalmDB:

	def __init__(self):
		self.raw_data = None # contans unparsed PDB file

	def _init_header(self):
		self.header = self.raw_data[0:80] # fixed size byte array
		self.dbname, ignore, ignore = self.header[0:32].partition('\0') # null-terminated string inside of fixed-size array
		self.format_version = ConstBitArray(bytes=self.header[34:36]).uintbe # app-specific, big-endian
		self.dbtype = self.header[60:64] # 4 char app-specific identifier
		self.creator = self.header[64:68] # 4 char identifier assigned to the app

		# db attributes
		raw_attributes = ConstBitArray(bytes=self.header[32:34]) # bit array, see below
		self.attributes = {}
		self.attributes["resource"] = raw_attributes[15]
		self.attributes["readonly"] = raw_attributes[14]
		self.attributes["dirty"] = raw_attributes[13]
		self.attributes["archive"] = raw_attributes[12]
		self.attributes["rewritable"] = raw_attributes[11] # PalmOS 2+
		self.attributes["reset"] = raw_attributes[10] # PalmOS 2+
		self.attributes["protected"] = raw_attributes[9]
		self.attributes["syncable"] = not(raw_attributes[8]) # PalmOS 2+
		self.attributes["busy"] = raw_attributes[0]

		MAC_EPOCH = 2082844800L # number of seconds between Jan 1 1904 and Jan 1 1970

		creation_time = ConstBitArray(bytes=self.header[36:40]).uintbe # seconds since Mac epoch, big-endian
		modification_time = ConstBitArray(bytes=self.header[40:44]).uintbe # seconds since Mac epoch, big-endian (modification number [48:52] and seed [68:72] are unused)
		backup_time = ConstBitArray(bytes=self.header[44:48]).uintbe # seconds since Mac epoch, big-endian

		if creation_time > MAC_EPOCH:
			self.creation_time = datetime.datetime.fromtimestamp(creation_time - MAC_EPOCH)
		else:
			self.creation_time = None
		if modification_time > MAC_EPOCH:
			self.modification_time = datetime.datetime.fromtimestamp(modification_time - MAC_EPOCH)
		else:
			self.modification_time = None

		if backup_time > MAC_EPOCH:
			self.backup_time = datetime.datetime.fromtimestamp(backup_time - MAC_EPOCH)
		else:
			self.backup_time = None # weird: in my case backup_time always is 28800

		# recordlist (chained record lists are deprecated as of PalmOS 4, have no real use and discouraged in lower PalmOS versions => next recordlist [72:75] is unused)
		self.record_count = ConstBitArray(bytes=self.header[76:78]).uintbe # length of (first and the only) record list, big-endian
		self.recordlist_offset = ConstBitArray(bytes=self.header[78:80]).uintbe # array of pointers to real data, may be set to 0x0000 if there are no records

		# appinfo
		self.appinfo_offset = ConstBitArray(bytes=self.header[52:56]).uintbe # 0x0000 if not present, big-endian
		self.sortinfo_offset = ConstBitArray(bytes=self.header[56:60]).uintbe # immediately after appinfo, 0x0000 if not present, big-endian
		if self.appinfo_offset != 0:
			if self.sortinfo_offset != 0:
				appinfo_end = self.sortinfo_offset
			else:
				if self.recordlist_offset != 0: # no sortinfo
					appinfo_end = self.recordlist_offset
				else:
					appinfo_end = len(self.raw_data) # neither sortinfo nor records
			self.raw_appinfo = self.raw_data[self.appinfo_offset:appinfo_end] # app-specific
		else:
			self.raw_appinfo = None

		# standard PalmOS categories (part of appinfo, not mandatory - apps may define a different format but builtin PIM apps use them)
		self.categories = {} # this cannot be an array because records reference the categories via original position (and they don't have to be a contiguous sequence)
		for category_num in range(16):
			category_name, ignore1, ignore2 = self.raw_appinfo[2 + category_num * 16 : 18 + category_num * 16].partition('\0') # null-terminated string, max. 15 chars + \0 (renamed categories [0:2] are ignored)
			if category_name:
				self.categories[category_num] = category_name # skip unused categories (with empty names) scattered among valid categories but preserve their original position as index
				# as the categories are referenced by records via order of appearance and not via category IDs, category IDs [258 + category_num] and last category ID [274] are ignored
		if not self.categories:
			self.categories[0] = "Unfiled" # fix for Datebook (has no category entries defined and last category ID is zero)

		# optional app-specific appinfo parsing (add your custom formats here)
		if self.creator == "addr":
			raw_labels = self.raw_appinfo[282:282+23*16] # some labels may be globally renamed, appinfo contains all their names (including defaults - renamed labels bitfield is ignored)
			self.labels = {}
			for label_num in range(22):
				label_name, ignore1, ignore2 = raw_labels[label_num * 16 : label_num * 16 + 16].partition('\0') # null-terminated string, max. 15 chars + \0
				self.labels[label_num] = label_name
			# country = ConstBitArray(bytes=self.raw_appinfo[634:636]).uintbe
			# sort_by_company = ConstBitArray(bytes=self.raw_appinfo[636:638])[0]

		# sortinfo
		if self.sortinfo_offset != 0:
			if self.recordlist_offset:
				sortinfo_end = self.recordlist_offset
			else:
				sorinfo_end = len(self.raw_data) # no records
			self.raw_sortinfo = self.raw_data[self.sortinfo_offset:sorinfo_end] # app-specific
		else:
			self.raw_sortinfo = None

	def _init_records(self):
		self.raw_records = [] # app-specific, each record is stored as a dict
		offset = 78 + self.recordlist_offset # pointer to pointer to first real data

		# find the real data
		for record_num in range(self.record_count):
			record_offset = ConstBitArray(bytes=self.raw_data[offset:offset + 4]).uintbe # pointer to real data
			raw_record_attributes = ConstBitArray(bytes=self.raw_data[offset + 4]) # attributes of real data, bitarray, see below (record ID [offset + 5: offset + 8] is unused)

			# record attributes
			record_attributes = {}
			record_attributes["deleted"] = raw_record_attributes[0]
			record_attributes["dirty"] = raw_record_attributes[1]
			record_attributes["busy"] = raw_record_attributes[2]
			record_attributes["secret"] = raw_record_attributes[3]
			record_attributes["category"] = self.categories[ raw_record_attributes[4:8].uint ] # record category is a 4-bit number (not category ID)

			# length of real data
			if record_num < self.record_count - 1:
				next_record_offset = ConstBitArray(bytes=self.raw_data[offset + 8:offset + 12]).uintbe # pointer to next data
			else:
				next_record_offset = len(self.raw_data) # or pointer to EOF if this is the last record

			raw_record = self.raw_data[record_offset:next_record_offset] # get real data

			# app-specific raw record parsing (add your custom record formats here)
			record = None
			if self.creator == "todo":
				record = ToDoRecord(raw_record)
			if self.creator == "memo":
				record = MemoRecord(raw_record)
			if self.creator == "addr":
				record = AddressBookRecord(raw_record, self.labels) # label names may be customized
			if self.creator == "date":
				record = DateBookRecord(raw_record)

			self.raw_records.append( { 'raw': raw_record, 'attributes': record_attributes, "record": record } )
			offset += 8 # next record

	def __str__(self):
		retval = "%s (%s, %s): %s records" % (self.dbname, self.creator, self.dbtype, self.record_count)
		retval += ", categories: " + str(self.categories)
		retval += ", attributes: " + str(self.attributes)
		return retval

	def load(self, filename):
		f = open(filename, 'r')
		self.raw_data = f.read() # as PDB files are relatively small (<100KB) we don't care about RAM demands
		f.close()
		self._init_header()
		self._init_records()

	def from_string(self, string):
		self.raw_data = string
		self._init_header()
		self._init_records()

if __name__ == '__main__':

	import sys

	db = PalmDB()
	db.load(sys.argv[1])

	print db

	for record in db.raw_records:
		if record:
			print record["record"]
		else:
			print record["raw_record"]
