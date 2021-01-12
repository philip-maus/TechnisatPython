#  Copyright 2021 getNameFromUser
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at

#       http://www.apache.org/licenses/LICENSE-2.0

#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.


from typing import Union

import threading
import ffmpeg
import socket
import time
import os
import struct


class TechnisatFile(object):
    TYPE_DIRECTORY = 0
    TYPE_BINARY = 1
    TYPE_TS_RADIO = 3
    TYPE_TS_SD = 4
    TYPE_TS_HD = 7
    TYPE_USB = 9

    EXTENSIONS = {
        TYPE_TS_RADIO: "MP2",
        TYPE_TS_SD: "TS",
        TYPE_TS_HD: "TS4"
    }

    def __init__(self, recording_id, title, file_type, size, seconds_since_2000, description=""):
        self.recording_id = recording_id
        self.title = title
        self.file_type = file_type
        self.size = size
        self.date = seconds_since_2000 + 946684800
        self.description = description

    def __str__(self) -> str:
        append = ""
        timestamp = time.strftime("%d.%m.%Y - %H:%M:%S", time.gmtime(self.date))
        info = "(" + str(self.file_type) + ", " + str(self.size) + "B, " + timestamp + ")"
        if len(self.description) > 0:
            append = ": " + self.description
        return str(self.recording_id) + " : " + self.title + info + append


class Technisat(object):
    def __init__(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.files = {}
        self.idle = TechnisatIdleThread(self)
        self.is_connected = False

    def __read_num(self, t: Union[str, int] = "b") -> int:
        if type(t) == str:
            return struct.unpack(">" + t, self.socket.recv(struct.calcsize(">" + t)))[0]
        elif type(t) == int:
            return int.from_bytes(self.socket.recv(t), "big")
        else:
            raise TypeError()

    def __read_string(self) -> Union[str, None]:
        length = self.__read_num("B")  # First byte is length of string
        response = self.socket.recv(length)
        if len(response) == 0:
            return None
        if response[0] == 5 or response[0] == 11:
            return response[1:].decode("Latin-1")
        else:
            return response.decode("Latin-1")

    def connect(self, ip, port):
        self.socket.connect((ip, port))
        self.is_connected = True
        self.idle.start()

    def __disk_busy(self) -> bool:
        print("[E] Disk is busy!")
        time.sleep(1)
        return self.ok()

    def __disk_starting(self) -> bool:
        print("[I] Disk is starting up!")
        time.sleep(1)
        return self.ok()

    def __read_ok(self) -> bool:
        read = self.__read_num()
        if read == 1:
            return True
        elif read == -4:
            return self.__disk_busy()
        elif read == -7:
            return self.__disk_starting()
        else:
            return False

    def ok(self, lock=True) -> bool:
        if lock:
            self.idle.lock()
        self.socket.send(b'\x01')
        response = self.__read_ok()
        if lock:
            self.idle.unlock()
        return response

    def info(self):
        self.idle.lock()
        self.socket.send(b'\x02')
        flags = self.socket.recv(5)
        lang = self.socket.recv(3).decode("Latin-1")
        name = self.__read_string()
        self.socket.send(b'\x01')
        self.idle.unlock()
        return flags, lang, name

    def ls(self, directory="/"):
        self.idle.lock()
        root = len(directory) == 0 or directory == "/"
        directories = list(filter(lambda item: item != '', directory.split("/")))

        if root:
            self.socket.send(b'\x03\x00\x00')
        else:
            self.socket.send(b'\x03\x00\x01')

        self.__read_ok()
        if not root:
            self.socket.send(bytes("/".join(directories), "ascii"))
            self.socket.recv(1)
            self.ok()

        current_dir = self.files
        for d in directories:
            if d in current_dir:
                current_dir = current_dir[d]
            else:
                raise FileNotFoundError

        if type(current_dir) is not dict:
            raise NotADirectoryError

        file_count = self.__read_num("H")  # filecount is short

        for i in range(file_count):  # read every file
            file_type = self.__read_num()  # file type is first byte in "file response"

            if file_type == TechnisatFile.TYPE_DIRECTORY:
                self.__read_num()
                file_name = self.__read_string()
                current_dir[file_name] = {}
            elif file_type == TechnisatFile.TYPE_BINARY:
                file_name = self.__read_string()
                file_size = self.__read_num("Q")
                seconds_since_2000 = self.__read_num("I")
                current_dir[file_name] = TechnisatFile(-1, file_name, file_type, file_size, seconds_since_2000)
            elif file_type == TechnisatFile.TYPE_USB:
                self.__read_num()
                description = self.__read_string()
                file_name = self.__read_string()
                current_dir[file_name] = TechnisatFile(-1, file_name, file_type, -1, -1, description=description)
            else:
                self.__read_num()
                recording_id = self.__read_num("B")  # recording id is third byte in "file response"
                file_name = self.__read_string()
                file_size = self.__read_num("Q")  # file size is next 8 bytes
                seconds_since_2000 = self.__read_num("L")  # seconds since 2000 -> next 4 bytes
                current_dir[file_name] = TechnisatFile(recording_id, file_name, file_type, file_size,
                                                       seconds_since_2000)

        self.idle.unlock()
        return current_dir

    def download(self, file: TechnisatFile, destination, output_format="mp4", resolution=""):
        self.idle.lock()
        self.socket.send(bytes([5]) + struct.pack('>H', file.recording_id) + struct.pack('Q', 0))
        print("Starting download of \"" + file.title + "\": ", end='')
        self.__read_num()
        print("OK")
        file_size = self.__read_num("Q")
        print("Expected File Size: " + str(file_size))
        file_count = self.__read_num("B")
        print("File count: " + str(file_count))
        files = []
        directory = os.path.join(destination, file.title)
        if not os.path.isdir(directory):
            os.makedirs(directory)

        for i in range(file_count):
            file_number = self.__read_num("B")
            file_extension = self.__read_string()
            files.append(open(os.path.join(directory, "download." + file_extension), "wb"))
            print("File No. " + str(file_number) + ": " + os.path.join(directory, "download." + file_extension))
        self.socket.send(b'\x01')

        print("Downloading", end='')
        status = 0
        while True:
            file_number = self.__read_num()
            status = (status + 1) % 20
            if status == 0:
                print(".", end='')
            if file_number >= 0:
                chunk_size = self.__read_num("I")
                self.socket.recv(3)
                r = bytearray()
                i = 0
                while i < chunk_size:
                    sub_chunk = self.socket.recv(chunk_size - i)
                    r += sub_chunk
                    i += len(sub_chunk)

                files[file_number].write(r)
            elif file_number == -4 or file_number == -7:
                print("Device busy! ")
            else:
                self.idle.unlock()
                for f in files:
                    f.close()
                print("Transfer done", end='')
                ext = TechnisatFile.EXTENSIONS.get(file.file_type, "")
                if len(output_format) > 0 and len(ext) > 0:
                    print(", converting to " + output_format)
                    if len(resolution) > 0:
                        ffmpeg.input(os.path.join(directory, "download." + ext)) \
                            .output(os.path.join(directory, "download." + output_format),
                                    **{'vf': ("scale=" + resolution)}).run()
                    else:
                        ffmpeg.input(os.path.join(directory, "download." + ext)) \
                            .output(os.path.join(directory, "download." + output_format)).run()
                    print("Done!")
                else:
                    print("!")

                return True

    def disconnect(self):
        self.idle.cancel()
        self.idle = None
        self.socket.close()
        self.is_connected = False

    def _resolve_id(self, recording_id: int, current_dict: dict) -> Union[TechnisatFile, None]:
        for v in current_dict.values():
            if type(v) is TechnisatFile and v.recording_id == recording_id:
                return v
            elif type(v) is dict:
                found = self._resolve_id(recording_id, v)
                if found is not None:
                    return found

        return None

    def resolve_id(self, recording_id: int) -> Union[TechnisatFile, None]:
        return self._resolve_id(recording_id, self.files)


class TechnisatIdleThread(threading.Thread):

    def __init__(self, receiver: Technisat):
        threading.Thread.__init__(self)
        self.receiver = receiver
        self.unlocked = threading.Event()
        self.sent = threading.Event()
        self.stop = threading.Event()
        self.unlocked.set()
        self.sent.set()

    def run(self):
        while not self.stop.is_set():
            self.unlocked.wait()
            self.sent.clear()
            # noinspection PyBroadException
            try:
                self.receiver.ok(False)
                self.sent.set()
            except:
                self.receiver.is_connected = False
                self.sent.set()
                self.lock()
            time.sleep(1)

    def lock(self):
        self.unlocked.clear()
        self.sent.wait()

    def unlock(self):
        self.unlocked.set()

    def cancel(self):
        self.stop.set()
