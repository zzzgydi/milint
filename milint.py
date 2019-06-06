# -*- coding: utf-8 -*-
'''
 Author: GyDi
 Date: 2019.6.6
'''
import sys, re, os, shutil
import getopt
import requests
import threading
import queue
import time

MiLint_Version = '2.0'
MiLint_HELP = '''Usage:
  -t <target file>      # 设置检查的 文件夹或者文件
  -a <assets>           # 设置存放的文件夹名称，默认'assets'文件夹
  -i <!dirs!..>         # 忽略某文件夹，仅在检查文件夹状态下有效，用'!'隔开多个
  -m <thread num>       # 开启多线程处理，输入线程数，不合理的数将使用默认的值
  -o open net check     # 开启网络路径图片有效性检查，默认不开启
  -c close rel check    # 关闭相对路径图片有效性检查，默认开启
  -l open info log      # 开启Info级别的提示，默认关闭
  -h Help               # 查看帮助
  -v Version            # 查看版本'''


# MiLint 配置类
class MiLintConf():

    def __init__(self):
        self.target = ''  # 设置检查的路径，可以是文件夹或者md文件
        self.targetType = ''  # 是文件还是文件夹
        self.assets = 'assets'  # 默认将md中的图片放在md目录下的assets文件夹
        self.isCheckNet = False  # 是否检查网络路径的图片
        self.isCheckRel = True  # 是否检查相对路径的图片
        self.isIgnore = False  # 是否要忽略文件夹，用于判断
        self.isMultiThread = False  # 是否用多线程处理文件夹的
        self.isLogInfo = False  # 是否打印info级别的信息
        self.ignoreDirs = []  # 可以选择忽略某个文件夹的文件
        self.threadNum = 4  # 多线程状态下的线程数，默认为4
        pass

    def logError(self, msg):
        print('[Error]:', msg)

    def setTarget(self, target):
        target = os.path.abspath(target)
        if os.path.isdir(target):
            self.targetType = 'dir'
        elif os.path.isfile(target):
            if target.find('.md') == -1:
                self.logError('Target File must be a Markdown.')
                return False
            self.targetType = 'file'
        else:
            self.logError('Invalid Target path.')
            return False
        self.target = target
        return True

    def setAssets(self, assets):
        self.assets = assets.lstrip('\\/.')
        if assets.find('.') != -1:
            self.logError('Invalid assets name.')
            return False
        return True

    def setIgnoreDirs(self, ignore):
        self.ignoreDirs = [elem for elem in ignore.split('!') if elem != '']
        self.isIgnore = True if len(self.ignoreDirs) > 0 else False

    def setThreadNum(self, arg):
        self.threadNum = int(re.sub(r'\D', '', arg))
        self.threadNum = self.threadNum if self.threadNum > 0 else 4
        self.isMultiThread = True


class MiLint():
    _reRelPath = re.compile(
        r"^(?:\.{1,2}[\\/]{1,2})*(?:[^\.\\/:]+[\\/]{1,2})*[^\.:]*(?:\.[^\.:]+)?")  # 相对路径
    _reNetPath = re.compile(r"[a-zA-z]+://[^\s]*")  # 网络路径
    _reImgPatt = re.compile(r"(.*?)!\[(.*?)\]\((.+)\)(.*)")  # 匹配md中的图片语法
    _reSplitPath = re.compile(r"[\\/]{1,2}")
    _reReplace = re.compile(r'\\{1,2}|//')

    def __init__(self, conf):
        if not isinstance(conf, MiLintConf):
            raise TypeError('Invalid config object.')
        self.conf = conf  # 配置项
        self.fileQueue = queue.Queue()  # 文件队列
        self.lock = threading.Lock()

    # 判断是否是相对路径
    @staticmethod
    def isRelPath(path):
        if path == '.' or path == '..':
            return True
        tmp = MiLint._reRelPath.match(path)
        return tmp and tmp.group() == path

    # 判断是否是网络路径
    @staticmethod
    def isNetPath(path):
        tmp = MiLint._reNetPath.match(path)
        return tmp and tmp.group() == path

    # 判断路径类型 有相对路径、绝对路径、网络路径
    @staticmethod
    def getPathType(path):
        if os.path.isabs(path):
            return 'abs'
        if MiLint.isRelPath(path):
            return 'rel'
        if MiLint.isNetPath(path):
            return 'net'
        return None

    # 将相对路径中的 反斜杠 转成斜杆
    @staticmethod
    def reviseRelPath(path):
        return re.sub(MiLint._reReplace, '/', path)

    # 用于检查相对路径下的文件是否可以访问，传入参数，md文件的路径（绝对），图片路径（相对）
    @staticmethod
    def checkRelPath(filePath, imgPath):
        if os.path.isfile(filePath):
            filePath = os.path.dirname(filePath)
        for i in MiLint._reSplitPath.split(imgPath):
            if i == '..':
                filePath = os.path.dirname(filePath)
            elif i != '.':
                filePath = os.path.join(filePath, i)
        return os.path.exists(filePath)

    # 用于检查网络路径的图片是否可用
    @staticmethod
    def checkNetPath(path):
        return requests.get(path).status_code == 200

    # 打印错误信息
    def logError(self, msg, arg1=None, arg2=None):
        if arg1 and arg2:
            print("[Error]: {} File: {} (Line: {})".format(msg, arg1, arg2))
        else:
            print('[Error]:', msg)

    # 打印提示信息
    def logInfo(self, msg):
        if not self.conf.isLogInfo:
            return
        print('[Info]:', msg)
        pass

    # 条件递归获取文件  生产者
    def findAllMarkdowns(self, root):
        dirs = os.listdir(root)
        for i in dirs:
            tmp = os.path.join(root, i)
            if os.path.isdir(tmp):
                if not self.conf.isIgnore or i not in self.conf.ignoreDirs:
                    self.findAllMarkdowns(tmp)
            elif os.path.isfile(tmp) and i.find('.md') != -1:
                self.fileQueue.put(tmp)

    # 检查一个文件
    def inspectFile(self, filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            self.logError('File({}) decode error, experted utf-8.'.format(filename))
            return
        outstrs, workstack, num = [], [], 0
        self.logInfo('Checking file {}...'.format(filename))
        for line in lines:
            num += 1
            res = MiLint._reImgPatt.match(line)
            if not res:
                outstrs.append(line)
                continue
            prefix, desc, path, postfix = res.groups()
            pathType = MiLint.getPathType(path)
            if pathType == 'rel':
                path = MiLint.reviseRelPath(path)
                if self.conf.isCheckRel and not MiLint.checkRelPath(filename, path):
                    self.logError('Image not found.', filename, num)
            elif pathType == 'abs':
                dst = os.path.join(
                    os.path.dirname(filename), self.conf.assets, os.path.basename(path))
                workstack.append({'src': path, 'dst': dst, 'line': num})
                path = self.conf.assets + '/' + os.path.basename(path)
            elif pathType == 'net':
                if self.conf.isCheckNet and not MiLint.checkNetPath(path):  # 阻塞时间超长
                    self.logError('Invalid URL.', filename, num)
            else:
                self.logError('Invalid or unexperted image path.', filename, num)
            outstrs.append('{}![{}]({}){}\n'.format(prefix, desc, path, postfix))
        for each in workstack:
            if not os.path.exists(os.path.dirname(each['dst'])):
                self.logInfo('New a folder {}.'.format(os.path.dirname(each['dst'])))
                os.mkdir(os.path.dirname(each['dst']))
            if not os.path.isfile(each['src']):
                self.logError('Source Image not found.', filename, each['line'])
                outstrs[each['line'] - 1] = lines[each['line'] - 1]  # 找不到图片 不改变原来的路径
                continue
            if not os.path.exists(each['dst']):
                self.logInfo('Copying Image to {}.'.format(each['dst']))
                shutil.copyfile(each['src'], each['dst'])
        with open(filename, 'w', encoding='utf-8') as fw:
            fw.write(''.join(outstrs))

    # 多线程的执行者
    @staticmethod
    def _multiRunner(obj):
        while not obj.fileQueue.empty():
            obj.lock.acquire()
            filename = obj.fileQueue.get()
            obj.lock.release()
            obj.inspectFile(filename)

    # 多线程调度方法
    def __multiScheduler(self):
        threads = []
        for _ in range(self.conf.threadNum):
            lthread = threading.Thread(target=MiLint._multiRunner, args=(self,))
            lthread.start()
            threads.append(lthread)
        MiLint._multiRunner(self)
        for each in threads:
            each.join()

    # run
    def run(self):
        if self.conf.targetType == 'file':
            self.inspectFile(self.conf.target)
        elif self.conf.targetType == 'dir':
            self.findAllMarkdowns(self.conf.target)
            self.logInfo('Found {} files.'.format(self.fileQueue.qsize()))
            if self.conf.isMultiThread:
                self.__multiScheduler()
            else:
                while not self.fileQueue.empty():
                    self.inspectFile(self.fileQueue.get())
        else:
            self.logError('Must set a dir or a file.')


# 处理输入参数
def handleArgv():
    conf = MiLintConf()
    try:
        opts, _ = getopt.getopt(sys.argv[1:], "t:a:i:m:oclhv", [])
    except getopt.GetoptError as e:
        print('[Error]:', e)
        print(MiLint_HELP)
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-t':
            if not conf.setTarget(arg):
                sys.exit(2)
        elif opt == '-a':
            conf.setAssets(arg)
        elif opt == '-i':
            conf.setIgnoreDirs(arg)
        elif opt == '-m':
            conf.setThreadNum(arg)
        elif opt == '-o':
            conf.isCheckNet = True
        elif opt == '-c':
            conf.isCheckRel = False
        elif opt == '-l':
            conf.isLogInfo = True
        elif opt == '-h':
            print(MiLint_HELP)
            sys.exit(0)
        elif opt == '-v':
            print('Version:', MiLint_Version)
            sys.exit(0)
        else:
            print('[Warn]: Unexpected argument {}.'.format(opt))
    if conf.targetType == '':
        print('[Error]: Must set a dir or a file, use -t.')
        sys.exit(2)
    return conf


if __name__ == '__main__':
    time_start = time.time()
    milint = MiLint(handleArgv())
    milint.run()
    print('=== MiLint work finished, cost {:.4f}s ==='.format(time.time() - time_start))
