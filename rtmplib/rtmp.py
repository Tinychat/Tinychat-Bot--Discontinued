import logging
import random
import socket
import struct
import time

import pyamf.util.pure

from . import packet, reader, writer, rtmp_type, socks


log = logging.getLogger(__name__)


class FileDataTypeMixIn(pyamf.util.pure.DataTypeMixIn):
    """
    Provides a wrapper for a file object that enables reading and writing of raw
    data types for the file.
    """
    def __init__(self, fileobject):
        self.fileobject = fileobject
        pyamf.util.pure.DataTypeMixIn.__init__(self)

    def read(self, length):
        return self.fileobject.read(length)

    def write(self, data):
        self.fileobject.write(data)

    def flush(self):
        self.fileobject.flush()

    @staticmethod
    def at_eof():
        return False


class RtmpClient:
    """ Represents an RTMP client. """
    def __init__(self, ip, port, tc_url, app, **kwargs):
        """ Initialize a new RTMP client. """
        self.ip = ip
        self.port = port
        self.tc_url = tc_url
        self.app = app
        self.page_url = kwargs.get('page_url', u'')
        self.swf_url = kwargs.get('swf_url', u'')
        self.proxy = kwargs.get('proxy', '')
        self.is_win = kwargs.get('is_win', False)
        self.flash_version = kwargs.get('flash_version', 'WIN 22.0.0.209')
        self.shared_objects = []
        self.socket = None
        self.stream = None
        self.file = None
        self.writer = None
        self.reader = None

        self.stream_id = 0
        self._transaction_id = 2

    @staticmethod
    def create_random_bytes(length, readable=False):
        """ Creates random bytes for the handshake. """
        ran_bytes = ''
        i, j = 0, 0xff
        if readable:
            i, j = 0x41, 0x7a
        for x in xrange(0, length):
            ran_bytes += chr(random.randint(i, j))
        return ran_bytes

    def handshake(self):
        """ Perform the handshake sequence with the server. """
        self.stream.write_uchar(3)
        c1 = packet.Handshake()
        c1.first = 0
        c1.second = 0
        c1.payload = self.create_random_bytes(1528)
        c1.encode(self.stream)
        self.stream.flush()

        self.stream.read_uchar()
        s1 = packet.Handshake()
        s1.decode(self.stream)

        c2 = packet.Handshake()
        c2.first = s1.first
        c2.second = s1.second
        c2.payload = s1.payload
        c2.encode(self.stream)
        self.stream.flush()

        s2 = packet.Handshake()
        s2.decode(self.stream)

    def connect_rtmp(self, connect_params):
        """ Initiate a NetConnection with a Flash Media Server. """
        msg = {
            'msg': rtmp_type.DT_COMMAND,
            'command':
            [
                u'connect',
                1,
                {
                    'videoCodecs': 252,
                    'audioCodecs': 3575,
                    'flashVer': u'' + self.flash_version,
                    'app': self.app,
                    'tcUrl': self.tc_url,
                    'videoFunction': 1,
                    'capabilities': 239,
                    'pageUrl': self.page_url,
                    'fpad': False,
                    'swfUrl': self.swf_url,
                    'objectEncoding': 0
                }
            ]
        }
        if type(connect_params) is dict:
            msg['command'].append(connect_params)
        else:
            msg['command'].extend(connect_params)

        self.writer.write(msg)
        self.writer.flush()

    def handle_packet(self, amf_data):
        """ Handle packets based on data type."""
        if amf_data['msg'] == rtmp_type.DT_USER_CONTROL and amf_data['event_type'] == rtmp_type.UC_PING_REQUEST:
            resp = {
                'msg': rtmp_type.DT_USER_CONTROL,
                'event_type': rtmp_type.UC_PING_RESPONSE,
                'event_data': amf_data['event_data'],
            }
            self.writer.write(resp)
            self.writer.flush()
            return True

        elif amf_data['msg'] == rtmp_type.DT_USER_CONTROL and amf_data['event_type'] == rtmp_type.UC_PING_RESPONSE:
            unpacked_tpl = struct.unpack('>I', amf_data['event_data'])
            unpacked_response = unpacked_tpl[0]
            log.debug('ping response from server %s' % unpacked_response)
            return True

        elif amf_data['msg'] == rtmp_type.DT_WINDOW_ACK_SIZE:
            assert amf_data['window_ack_size'] == 2500000, amf_data
            ack_msg = {'msg': rtmp_type.DT_WINDOW_ACK_SIZE, 'window_ack_size': amf_data['window_ack_size']}
            self.writer.write(ack_msg)
            self.writer.flush()
            return True

        elif amf_data['msg'] == rtmp_type.DT_SET_PEER_BANDWIDTH:
            assert amf_data['window_ack_size'] == 2500000, amf_data
            assert amf_data['limit_type'] == 2, amf_data
            return True

        elif amf_data['msg'] == rtmp_type.DT_USER_CONTROL and amf_data['event_type'] == rtmp_type.UC_STREAM_BEGIN:
            assert amf_data['event_type'] == rtmp_type.UC_STREAM_BEGIN, amf_data
            assert amf_data['event_data'] == '\x00\x00\x00\x00', amf_data
            return True

        elif amf_data['msg'] == rtmp_type.DT_SET_CHUNK_SIZE:
            assert 0 < amf_data['chunk_size'] <= 65536, amf_data
            self.reader.chunk_size = amf_data['chunk_size']
            return True

        else:
            return False

    # create stream test
    def is_create_stream_response(self, amf_data):
        if amf_data['msg'] == rtmp_type.DT_COMMAND and len(amf_data['command']) is 4:
            if amf_data['command'][0] == '_result' and type(amf_data['command'][3]) is int:
                log.info('create stream response received, stream id : %s' % amf_data['command'][3])
                self.stream_id = amf_data['command'][3]
                self.writer.stream_id = self.stream_id
                return True
            return False
        return False

    def call(self, process_name, parameters=None, trans_id=0):
        """ Runs remote procedure calls (RPC) at the receiving end. """
        if parameters is None:
            parameters = []  # parameters = {}
        msg = {
            'msg': rtmp_type.DT_COMMAND,
            'command':
            [
                process_name,
                trans_id,
                parameters
            ]
        }
        self.writer.write(msg)
        self.writer.flush()

    def connect(self, connect_params=None):
        """ Connect to the server with the given connect parameters. """
        if self.proxy:
            parts = self.proxy.split(':')
            ip = parts[0]
            port = int(parts[1])

            ps = socks.socksocket()
            ps.set_proxy(socks.HTTP, addr=ip, port=port)
            self.socket = ps
        else:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.socket.connect((self.ip, self.port))
        self.file = self.socket.makefile()
        self.stream = FileDataTypeMixIn(self.file)

        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if self.is_win:
            self.socket.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 10000, 3000))

        self.handshake()

        self.reader = reader.RtmpReader(self.stream)
        self.writer = writer.RtmpWriter(self.stream)

        self.connect_rtmp(connect_params)

    def shutdown(self):
        """ Closes the socket connection. """
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
            self.socket.close()
        except socket.error as se:
            log.error('socket error %s' % se)

    def shared_object_use(self, so):
        """ Use a shared object and add it to the managed list of SOs. """
        if so in self.shared_objects:
            return
        so.use(self.reader, self.writer)
        self.shared_objects.append(so)

    def ping_request(self):
        """
        Send a PING request.
        NOTE: I think its highly unlikely that a client would send this to a server,
        it's usually the other way around, the sever sends this to the client to make sure the client is alive.
        It does seem like some servers(all?) respond to this.
        """
        msg = {
            'msg': rtmp_type.DT_USER_CONTROL,
            'event_type': rtmp_type.UC_PING_REQUEST,
            'event_data': struct.pack('>I', int(time.time()))
        }
        log.debug('sending ping request to server: %s' % msg)
        self.writer.write(msg)
        self.writer.flush()

    def _get_next_transaction_id(self):
        """ Get the next transaction ID. """
        transaction_id = self._transaction_id
        self._transaction_id += 1
        if self._transaction_id > 8388607:
            self._transaction_id = 2
        return transaction_id

    def createstream(self):
        """ Send createStream message. """
        msg = {
            'msg': rtmp_type.DT_COMMAND,
            'command': ['createStream', self._get_next_transaction_id(), None]
        }
        self.writer.write(msg)
        self.writer.flush()

    def closestream(self):
        """ Send closeStream message. """
        msg = {
            'msg': rtmp_type.DT_COMMAND,
            'command': ['closeStream', 0, None]
        }
        self.writer.write(msg)
        self.writer.flush()

    def deletestream(self):
        """ Send deleteStream message. """
        msg = {
            'msg': rtmp_type.DT_COMMAND,
            'command': ['deleteStream', 0, None]
        }
        self.writer.write(msg)
        self.writer.flush()

    def publish(self, publishing_name, publishing_type='live'):
        """
        Send publish message.
        :param publishing_name: the name of the stream to publish
        :param publishing_type: str publishing type. 'live, 'record' or 'append'
        """
        msg = {
            'msg': rtmp_type.DT_COMMAND,
            'command': ['publish', 0, None, str(publishing_name), publishing_type]
        }
        self.writer.write(msg)
        self.writer.flush()
