# Export data from built-in Palm PIM applications to plaintext

Expected usage:
- Make a backup of Palm database (.pdb) files (e.g. via pilot-xfer -b)
- Install Python 2
- Install "bitstring" Python package (sudo pip install bitstring)
- Run the script using python palm_db_parser.py <filename.pdb> > output.txt

Tested on Palm m5xx (PalmOS 4)

Note: The code is quite old - it used to work well along with bitstring 2.2.0.
