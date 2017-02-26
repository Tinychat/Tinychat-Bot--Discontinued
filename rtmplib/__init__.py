"""
This package is responsible for encoding/decoding RTMP amf messages.

This package contains classes/methods to establish a connection to a RTMP server
and to read/write amf messages on a connected stream.

It also contains the PySocks (https://github.com/Anorov/PySocks) module to enable
a connection to a RTMP server using a proxy.

It is a modified/edited version of the original made by prekageo(https://github.com/prekageo/rtmp-python)
containing some bug fixes, improvements and updates.
"""

__author__ = 'nortxort'
__authors__ = ['prekageo', 'Anorov', 'hydralabs', 'ruddernation-designs']
__credits__ = __authors__
