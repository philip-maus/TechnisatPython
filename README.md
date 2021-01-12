# TechnisatPython
Connect to your Technisat receiver, download and convert your recordings with a simple object oriented python api.

## Tested devices:
+ Technisat Digicorder HD S2+: Fully functional

## Required Software:
+ Python 3+
+ ffmpeg-python from pip: ```pip install ffmpeg-python```
+ ffmpeg

## Classes:
### Technisat
Manages the connection to the receiver and has methods for the available commands.
#### Attributes:
+ ```socket```: connection to the receiver
+ ```files```: read files from the server
+ ```idle```: thread to manage idle-connections (sends ACK every second)
+ ```is_connected```: wether a connection to the receiver is established
#### Methods:
+ ```connect(ip, port)```: connects to the receiver at ip:port
+ ```ok()```: weather the receiver is ready to accept commands
+ ```info()```: returns the flags, language and name of the receiver
+ ```ls(paht = "/")```: gets the files under path from the receiver and returns a TechnisatFile object
+ ```download(file: TechnisatFile, destination, output_format="mp4", resolution="")```: downloads and converts the file in the TechnisatFile object to the folder in destination. You can also specify an output format and a resolution which is supported by ffmpeg
+ ```disconnect()```: disconnects from the receiver
+ ```resolve_id()```: returns the TechnisatFile object corresponding to the recording id
### TechnisatFile
An instance of a remote file on the receiver.
#### Attributes:
+ ```recording_id```: unique recording id on the receiver
+ ```title```: file name
+ ```file_type```: file type in (directionary = 0, binary = 1, radio = 3, sd video = 4, hd video = 7, usb = 9). Feel free to open an issue if you find another type
+ ```size```: file size in bytes
+ ```date```: recording date as unix timestamp
+ ```description```: file description, if one exists
### Methods:
+ ```__str__```: converts the file into a human readable string.
