# Spec: CSV to JSON tool

`convert(csv_text)` returns a JSON string of an array of row objects keyed by the header row, using the csv module (quoted commas must work). Empty input returns '[]'. A `main(argv)` reads a file path from argv[1] and prints the converted JSON.
