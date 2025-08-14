import time
import socket
import struct
from enum import Enum, IntFlag
from huffman import Huffman
from bytereader import ByteReader

# https://wiki.zandronum.com/Launcher_protocol#Query_flags
class ServerQueryFlags(IntFlag):
    NAME                = 0x00000001
    URL                 = 0x00000002
    EMAIL               = 0x00000004
    MAPNAME             = 0x00000008
    MAXCLIENTS          = 0x00000010
    MAXPLAYERS          = 0x00000020
    PWADS               = 0x00000040
    GAMETYPE            = 0x00000080
    GAMENAME            = 0x00000100
    IWAD                = 0x00000200
    FORCEPASSWORD       = 0x00000400
    FORCEJOINPASSWORD   = 0x00000800
    GAMESKILL           = 0x00001000
    BOTSKILL            = 0x00002000
    DMFLAGS             = 0x00004000
    LIMITS              = 0x00010000
    TEAMDAMAGE          = 0x00020000
    TEAMSCORES          = 0x00040000  # DEPRECATED
    NUMPLAYERS          = 0x00080000
    PLAYERDATA          = 0x00100000
    TEAMINFO_NUMBER     = 0x00200000
    TEAMINFO_NAME       = 0x00400000
    TEAMINFO_COLOR      = 0x00800000
    TEAMINFO_SCORE      = 0x01000000
    TESTING_SERVER      = 0x02000000
    DATA_MD5SUM         = 0x04000000
    ALL_DMFLAGS         = 0x08000000
    SECURITY_SETTINGS   = 0x10000000
    OPTIONAL_WADS       = 0x20000000
    DEH                 = 0x40000000
    EXTENDED_INFO       = 0x80000000

class ServerQueryFlags2(IntFlag):
    PWAD_HASHES        = 0x00000001
    COUNTRY            = 0x00000002
    GAMEMODE_NAME      = 0x00000004
    GAMEMODE_SHORTNAME = 0x00000008
    VOICECHAT          = 0x00000010

# https://wiki.zandronum.com/Launcher_protocol#Challenge_packet
SERVER_LAUNCHER_CHALLENGE           = 5660023
SERVER_LAUNCHER_IGNORING            = 5660024
SERVER_LAUNCHER_BANNED              = 5660025
SERVER_LAUNCHER_CHALLENGE_SEGMENTED = 5660032


# https://wiki.zandronum.com/Launcher_protocol#Game_modes 
class ZandronumGamemode(Enum):
    COOPERATIVE = 0
    SURVIVAL = 1
    INVASION = 2
    DEATHMATCH = 3
    TEAMPLAY = 4
    DUEL = 5
    TERMINATOR = 6
    LASTMANSTANDING = 7
    TEAMLMS = 8
    POSSESSION = 9
    TEAMPOSSESSION = 10
    TEAMGAME = 11
    CTF = 12
    ONEFLAGCTF = 13
    SKULLTAG = 14
    DOMINATION = 15

class ZandronumTeam:
    name: str
    color: tuple[4]
    score: int

    def __init__(self):
        pass

class ZandronumPlayer:
    name: str
    frags: int
    ping: int
    spectating: bool
    bot: bool
    team: int
    time: int # in minutes

    def __init__(self):
        pass

class ZandronumServer:
    def __init__(self, hostname: str, port: int):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(5) # 5 seconds
        self._hostname = hostname
        self._port = port

        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        
        # Initialize all attributes
        self.version = ''
        self.name = ''
        self.url = ''
        self.email = ''
        self.mapname = ''
        self.maxclients = 0
        self.maxplayers = 0
        self.pwads = []
        self.gametype = ZandronumGamemode.COOPERATIVE
        self.instagib = False
        self.buckshot = False
        self.gamename = ''
        self.iwad = ''
        self.forcepassword = False
        self.forcejoinpassword = False
        self.skill = 0
        self.botskill = 0
        self.dmflags = 0
        self.dmflags2 = 0
        self.zadmflags = 0
        self.compatflags = 0
        self.zacompatflags = 0
        self.compatflags2 = 0
        self.numplayers = 0
        self.players = []
        self.fraglimit = 0
        self.timelimit = 0
        self.timeleft = 0
        self.duellimit = 0
        self.pointlimit = 0
        self.winlimit = 0
        self.teamdamage = 0.0
        self.numteams = 0
        self.teams = []
        self.testing = False
        self.deh = []

    def _send(self, data: bytes) -> int:
        return self._sock.sendto(Huffman.encode(data), (self._hostname, self._port))

    def _recv(self, bufsize: int) -> ByteReader:
        try:
            data, _ = self._sock.recvfrom(bufsize)
        except socket.timeout:
            raise TimeoutError('Connection timed out while waiting for response from server.')
        except socket.error as e:
            raise ConnectionError(f'Could not receive data from server. Error: {e}')

        data = ByteReader(Huffman.decode(data))

        if data.remaining() < 4:
            raise ValueError("Received empty response")
        
        status = data.read_long()

        if status == SERVER_LAUNCHER_CHALLENGE:
            return data

        # UNTESTED CODE
        if status == SERVER_LAUNCHER_CHALLENGE_SEGMENTED:
            segments = {}

            while True:
                seg_number = data.read_byte()
                seg_total = data.read_byte()
                offset = data.read_short()
                size = data.read_short()
                total = data.read_short()

                segments[seg_number] = data.read_bytes(size)

                if len(segments) == seg_total:
                    full_data = b''.join(segments[i] for i in sorted(segments))
                    return ByteReader(full_data)

                data, _ = self._sock.recvfrom(bufsize)
                data = ByteReader(Huffman.decode(data))
                status = data.read_long()

                if status != SERVER_LAUNCHER_CHALLENGE_SEGMENTED:
                    raise ValueError("Unexpected packet")
        
        if status == SERVER_LAUNCHER_BANNED:
            raise ConnectionRefusedError('Server banned you.')
        
        if status == SERVER_LAUNCHER_IGNORING:
            raise ConnectionRefusedError('Server ignoring you.')

        raise ValueError(f'Unexpected server status ({status})! Remaining bytes: {data.remaining()}')

    def update_info(self, flags: ServerQueryFlags = 0xFFFFFFFF) -> ServerQueryFlags:
        request = b''
        request += struct.pack("<l", 199) # challenge
        request += struct.pack("<L", flags)
        request += struct.pack("<l", int(time.time()))
        
        try:
            self._send(request)

            res = self._recv(1024 * 8)

            send_time = res.read_long()
            self.version = res.read_string()
            res_flags = res.read_long()

            if res_flags & ServerQueryFlags.NAME:
                self.name = res.read_string()
            
            if res_flags & ServerQueryFlags.URL:
                self.url = res.read_string()

            if res_flags & ServerQueryFlags.EMAIL:
                self.email = res.read_string()
            
            if res_flags & ServerQueryFlags.MAPNAME:
                self.mapname = res.read_string()
            
            if res_flags & ServerQueryFlags.MAXCLIENTS:
                self.maxclients = res.read_byte()

            if res_flags & ServerQueryFlags.MAXPLAYERS:
                self.maxplayers = res.read_byte()

            if res_flags & ServerQueryFlags.PWADS:
                n = res.read_byte()
                self.pwads.clear()

                for i in range(n):
                    self.pwads.append(res.read_string())
            
            if res_flags & ServerQueryFlags.GAMETYPE:
                self.gametype = ZandronumGamemode(res.read_byte())
                self.instagib = res.read_byte()
                self.buckshot = res.read_byte()
            
            if res_flags & ServerQueryFlags.GAMENAME:
                self.gamename = res.read_string()

            if res_flags & ServerQueryFlags.IWAD:
                self.iwad = res.read_string()

            if res_flags & ServerQueryFlags.FORCEPASSWORD:
                self.forcepassword = res.read_byte()

            if res_flags & ServerQueryFlags.FORCEJOINPASSWORD:
                self.forcejoinpassword = res.read_byte()

            if res_flags & ServerQueryFlags.GAMESKILL:
                self.skill = res.read_byte()

            if res_flags & ServerQueryFlags.BOTSKILL:
                self.skill = res.read_byte()

            if res_flags & ServerQueryFlags.DMFLAGS:
                self.dmflags = res.read_long()
                self.dmflags2 = res.read_long()
                self.compatflags = res.read_long()
            
            if res_flags & ServerQueryFlags.LIMITS:
                self.fraglimit = res.read_short()
                self.timelimit = res.read_short()
                
                if self.timelimit > 0:
                    self.timeleft = res.read_short()

                self.duellimit = res.read_short()
                self.pointlimit = res.read_short()
                self.winlimit = res.read_short()

            if res_flags & ServerQueryFlags.TEAMDAMAGE:
                self.teamdamage = res.read_float()

            if res_flags & ServerQueryFlags.TEAMSCORES:
                res.read_short()
                res.read_short()

            if res_flags & ServerQueryFlags.NUMPLAYERS:
                self.numplayers = res.read_byte()

            if res_flags & ServerQueryFlags.PLAYERDATA:
                self.players.clear()

                for i in range(self.numplayers):
                    player = ZandronumPlayer()
                    player.name = res.read_string()
                    player.frags = res.read_short()
                    player.ping = res.read_short()
                    player.spectating = res.read_byte()
                    player.bot = res.read_byte()
                    player.team = res.read_byte()
                    player.time = res.read_byte()

                    self.players.append(player)
            
            if res_flags & ServerQueryFlags.TEAMINFO_NUMBER:
                self.numteams = res.read_byte()

            if res_flags & ServerQueryFlags.TEAMINFO_NAME:
                for i in range(self.numteams):
                    self.teams[i].name = res.read_string()

            if res_flags & ServerQueryFlags.TEAMINFO_COLOR:
                for i in range(self.numteams):
                    self.teams[i].color = struct.unpack("<BBBB", res.read_long())
            
            if res_flags & ServerQueryFlags.TEAMINFO_NAME:
                for i in range(self.numteams):
                    self.teams[i].name = res.read_short()

            if res_flags & ServerQueryFlags.TESTING_SERVER:
                self.testing = res.read_byte()
                res.read_string()

            if res_flags & ServerQueryFlags.ALL_DMFLAGS:
                n = res.read_byte()

                if n > 0:
                    self.dmflags = res.read_long()
                if n > 1:
                    self.dmflags2 = res.read_long()
                if n > 3:
                    self.zadmflags = res.read_long()
                if n > 4:
                    self.compatflags = res.read_long()
                if n > 5:
                    self.zacompatflags = res.read_long()
                if n > 6:
                    self.compatflags2 = res.read_long()

            return res_flags
        except Exception as e:
            print(f'Error has occured while updating doom server: {e}')