# coding=utf-8

import logging, os, threading, time
from logging.handlers import MemoryHandler

from .trace import handle_exception, Trace, Traceable, LogException


__version__ = '1.0.0'


LoggerClass = logging.getLoggerClass()


class SimpleLogger(object):
    """
    A SimpleLogger wraps an instance of logging.Logger with name the argument filename,
    use it like a file object calling write method.

    E.g., Create and use TimedRotatingLogger:
    >>> logger = SimpleLogger('filename')
    >>> logger.write('msg', 'error')
    """

    def __init__(self, filename, level='debug'):
        self.filename = filename
        self.logger = logging.getLogger(filename)
        self.logger.setLevel(getattr(logging, level.upper()))
        self.logger.addHandler(logging.FileHandler(filename))

    def write(self, msg, level='debug'):
        return getattr(self.logger, level.lower())(msg)


def make_handler(filename, capacity=1, format="[%(levelname)s][%(asctime)s] at %(module)s.py:%(lineno)s: %(message)s", **verbose):
    """
    Factory function that return either a new instance of ``logging.Handler`` or ``_MemoryHandler``.

    :param filename:
        It will be passed to create a ``logging.FileHandler`` if argument capacity not greater then 1.
    :type filename:
        ``basestr``

    :param capacity:
        It will be passed to create a ``_MemoryHandler`` if its value greater then 1.
    :type capacity:
       ``int``

    :param format:
        Format string for the instance of ``logging.FileHandler``, default: "[%(levelname)s][%(asctime)s] at %(module)s.py:%(lineno)s: %(message)s"
    :type format:
       ``str``
    """

    if capacity > 1:
        return _MemoryHandler(filename, capacity, **verbose)
    if not os.path.exists(os.path.dirname(filename)):
        os.makedirs(os.path.dirname(filename))
    handler = logging.FileHandler(filename)
    handler.setFormatter(logging.Formatter(format))
    return handler


class TimedRotatingLogger(logging.getLoggerClass()):
    """
    This class inherits ``logging.Logger`` and extends a method named rotate_handler to auto rotate log file in time
    depends on the argument suffixFmt. A ``TimedRotatingLogger`` just maintains a handler.
    created by call make_handler.

    :param file:
        Base filename, namespace will be used if it's omitted.
    :type file:
        ``basestr``

    :param level:
        Keyword argument. Logger level, default: 'INFO'.
    :type level:
        ``str`` = {"DEBUG"|"INFO"|"WARNING"|"CRITICAL"|"ERROR"}

    :param suffixFmt:
        Keyword argument. It will be used to call time.strftime(suffixFmt) to get the suffix of filename,
        ie: filename = baseFilename + '.' + time.strftime(suffixFmt).
        default: "%Y-%m-%d", it means that the log file will be rotate every day at midnight.
    :type suffixFmt:
        ``str``

    :param format:
        Keyword argument. Format string for instance of ``logging.FileHandler`` created by call make_handler.
    :type format:
       ``str``

    :param name:
        Keyword argument. The name of instance of ``TimedRotatingLogger``, the argument file will be used
        if it is omitted or None.
    :type format:
        ``str``

    E.g., Create and use TimedRotatingLogger:
    >>> logger = TimedRotatingLogger()
    >>> logger.info('msg')

    E.g., specify arguments:
    >>> logger = TimedRotatingLogger('filename', level='INFO', suffixFmt='%Y-%m-%d', name='error_log')
    >>> logger.info('msg')
    """

    def __init__(self, file=__name__, level='info', suffixFmt='%Y-%m-%d', name=None, **verbose):
        LoggerClass.__init__(self, name or file)
        self.handlers = list()
        self.setLevel(getattr(logging, level.upper()))
        self.__file = os.path.abspath(file)
        self.__suffixFmt = suffixFmt
        self.__suffix = time.strftime(self.__suffixFmt)
        self._rlock = threading.RLock()
        self.__verbose = verbose
        self.rotate_handler()

    def handle(self, record):
        if self.__suffix != time.strftime(self.__suffixFmt):
            with self._rlock:
                if self.__suffix != time.strftime(self.__suffixFmt):
                    self.__suffix = time.strftime(self.__suffixFmt)
                    self.rotate_handler()
        LoggerClass.handle(self, record)

    def rotate_handler(self):
        with self._rlock:
            for h in self.handlers:
                h.close()
            self.handlers = list()
            handler = make_handler(self.__file + '.' + self.__suffix, **self.__verbose)
            self.addHandler(handler)


class TimedRotatingMemoryLogger(TimedRotatingLogger):
    """
    This class inherits ``TimedRotatingLogger`` and extends a method named flush to flush buffering,
    auto flushing buffering was implemented.

    :param capacity:
        keyword argument, default: 100. If the buffering size equal the argument capacity,
        the ``_MemoryHandler`` will flush it.
    :type capacity:
        ``int`

    :param flushInterval:
        keyword argument, default: 120 second. Flush buffering if time.time() - theLastFlushTime greater then
        the argument flushInterval.
    :type flushInterval:
        ``int``

    :param flushLevel:
        keyword argument, default: 'ERROR'. Flush buffering if the level of a logRecord greater then or equal
        the argument flushLevel.
    :type flushLevel:
        ``str`` = {"DEBUG"|"INFO"|"WARNING"|"CRITICAL"|"ERROR"}
    """

    def __init__(self, **kwargs):
        kwargs.get('capacity') > 0 or kwargs.update(capacity=100)
        super(TimedRotatingMemoryLogger, self).__init__(**kwargs)

    def flush(self):
        with self._rlock:
            for h in self.handlers:
                h.flush()


class _MemoryHandler(MemoryHandler):
    def __init__(self, filename, capacity, **kwargs):
        flushLevel = getattr(logging, kwargs.get('flushLevel', 'ERROR').upper())
        target = make_handler(filename, capacity=1, **kwargs)
        MemoryHandler.__init__(self, capacity, flushLevel, target)
        self.__flushInterval = kwargs.get('flushInterval', 120.0)
        self.__lastFlushTime = time.time()
        self.__condition = threading.Condition()
        self.__flusher = None

    def shouldFlush(self, record):
        return MemoryHandler.shouldFlush(self, record) or (time.time() - self.__lastFlushTime > self.__flushInterval)\
               or (record.levelno >= self.flushLevel)

    def flush(self):
        with self.__condition:
            try:
                target, buffered, self.buffer = self.target, self.buffer, []
                self.__flusher = threading.Thread(target=self.__flush, args=(target, buffered,), name='flusher')
                self.__flusher.isDaemon() and self.__flusher.setDaemon(False)
                self.__flusher.start()
                self.__condition.wait(1.0)
            except Exception:
                self.buffer = buffered

    def __flush(self, target, buffered):
        with self.__condition:
            self.__condition.notifyAll()
        try:
            for record in buffered:
                target.handle(record)
            self.__lastFlushTime = time.time()
        except Exception:
            pass

    def close(self):
        self.flush()
        if self.__flusher and self.__flusher.is_alive():
            self.__flusher.join()
        MemoryHandler.close(self)
