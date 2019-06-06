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

MiLint_Version = '1.3'
MiLint_HELP = '''Usage:
  -d <dirname>          # 设置检查的文件夹
  -f <filename>         # 设置检查单一文件
  -a <assets>           # 设置存放的文件夹名称，默认'assets'文件夹
  -i <dirs>             # 忽略某文件夹，仅在检查文件夹状态下有效，用'!'隔开多个
  -m <thread num>       # 开启多线程处理，输入线程数，不合理的数将使用默认的值
  -o open net check     # 开启网络路径图片有效性检查，默认不开启
  -c close rel check    # 关闭相对路径图片有效性检查，默认开启
  -l open info log      # 开启Info级别的提示，默认关闭
  -h Help               # 查看帮助
  -v Version            # 查看版本'''


# MiLint配置类
class LintConf():
    workdir = ''  # 程序的遍历检查的根目录
    filename = ''  # 程序检查 单个文件
    assets = 'assets'  # 默认将md中的图片放在md目录下的assets文件夹
    checkNet = False  # 是否检查网络路径的图片
    checkRel = True  # 是否检查相对路径的图片
    ignoreDir = []  # 可以选择忽略某个文件夹的文件
    hasIgnore = False  # 判断是否要忽略文件夹，用于判断
    logInfo = False  # 是否打印Info信息
    useSingle = True  # 是否用单线程处理文件夹的
    threadNum = 4  # 多线程状态下的线程数，默认为4

    # 文件夹和文件 有且仅有一个
    def setWorkDir(self, wd):
        wd = os.path.abspath(wd)
        if not os.path.isdir(wd):
            print('[Error]: %s is not a dir.' % (wd,))
            return False
        self.workdir = wd
        return True

    def setFileName(self, fn):
        fn = os.path.abspath(fn)
        if not os.path.isfile(fn):
            print('[Error]: %s is not a file.' % (fn,))
            return False
        self.filename = fn
        return True

    # 设置改动之后的assets文件夹名称
    def setAssets(self, assets):
        self.assets = assets.lstrip('\\/.')

    # 设置忽略的名单
    def setIgnoreDir(self, ignore):
        dirs = ignore.split('!')
        self.ignoreDir = [elem for elem in dirs if elem != '']
        self.hasIgnore = True if len(self.ignoreDir) > 0 else False

    # 判断工作区是否正常，即输入 目标文件夹和目标文件 有且仅有一个
    def isParamNormal(self):
        if len(self.workdir) != 0 and len(self.filename) != 0:
            print('[Error]: Can only set a dir or a file.')
            return False
        if len(self.workdir) == 0 and len(self.filename) == 0:
            print('[Error]: Should set one target, Dir or File.')
            return False
        return True

    # 设置线程数
    def setThreadNum(self, arg):
        self.threadNum = int(re.sub(r'\D', '', arg))
        self.threadNum = self.threadNum if self.threadNum > 0 else 4
        self.useSingle = False


class Tool():
    # 相对路径
    _reRelPath = re.compile(
        r"^(?:\.{1,2}[\\/]{1,2})*(?:[^\.\\/:]+[\\/]{1,2})*[^\.:]*(?:\.[^\.:]+)?")
    # win绝对路径 能匹配类似 'C://../' 这种
    # _reAbsPath = re.compile(r"^([A-Z]:)([\\/]{1,2}[^\\/]*)*", re.I)
    # Linux绝对路径 能匹配 '/../..' 但不能匹配 '../'
    # _reAbsLPath = re.compile(r"^([\\/]{1,2}[^\\/]*)*")
    # 网络路径
    _reNetPath = re.compile(r"[a-zA-z]+://[^\s]*")
    # 匹配md中的图片语法
    _reImgPatt = re.compile(r"(.*?)!\[(.*?)\]\((.+)\)(.*)")
    # 用于切割路径的正则
    _reSplitPath = re.compile(r"[\\/]{1,2}")
    # 用于查找md文件的正则
    _reFindMd = re.compile(r".*?\.md$")

    # _reList = [(_reAbsPath, 'abs'), (_reAbsLPath, 'abs'), (_reRelPath, 'rel'),
    #           (_reNetPath, 'net')]

    # 判断是否是相对路径
    @staticmethod
    def _isRelPath(path):
        if path == '.' or path == '..':
            return True
        tmp = Tool._reRelPath.match(path)
        if tmp and tmp.group(0) == path:
            return True
        return False

    # 判断是否是网络路径
    @staticmethod
    def _isNetPath(path):
        tmp = Tool._reNetPath.match(path)
        if tmp and tmp.group(0) == path:
            return True
        return False

    # 判断路径类型 有相对路径、绝对路径、网络路径
    @staticmethod
    def getPathType(path):
        if os.path.isabs(path):
            return 'abs'
        if Tool._isRelPath(path):
            return 'rel'
        if Tool._isNetPath(path):
            return 'net'
        return None

    # 将相对路径中的 反斜杠 转成斜杆
    @staticmethod
    def reviseRelPath(path):
        return re.sub(r'\\{1,2}|//', '/', path)
        # return path.replace(r'\\{1,2}', '/')

    # 用于检查相对路径下的文件是否可以访问，传入参数，md文件的路径（绝对），图片路径（相对）
    @staticmethod
    def checkRelPath(filePath, imgPath):
        if os.path.isfile(filePath):
            filePath = os.path.dirname(filePath)
        for i in Tool._reSplitPath.split(imgPath):
            if i == '..':
                filePath = os.path.dirname(filePath)
            elif i != '.':
                filePath = os.path.join(filePath, i)
        return os.path.exists(filePath)

    # 用于检查网络路径的图片是否可用
    @staticmethod
    def checkNetPath(path):
        return requests.get(path).status_code == 200

    # 打印提示信息
    @staticmethod
    def printMsg(cnt, level, msg, argv1, argv2):
        print("[%s]: %s" % (level.capitalize(), msg))
        if cnt == 0:
            print("  File: %s (Line: %d)" % (argv1, argv2))
        elif cnt == 1:
            print("  From:", argv1)
            print("    To:", argv2)

    pass


conf = LintConf()  # 全局配置
filequeue = queue.Queue()  # 文件队列
lock = threading.Lock()


# 条件递归获取文件  生产者
def findAllMarkdownFile(root):
    dirs = os.listdir(root)
    for i in dirs:
        tmp = os.path.join(root, i)
        if os.path.isdir(tmp):
            if not conf.hasIgnore or i not in conf.ignoreDir:
                findAllMarkdownFile(tmp)
        elif os.path.isfile(tmp) and Tool._reFindMd.match(i):
            filequeue.put(tmp)
    pass


# 对每个文件的处理过程
def inspectFile(filename):
    outstrs, workstack, num = [], [], 0
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        print('[Error]: UnicodeDecodeError--Please use utf-8...')
        print('  File:', filename)
        return
    for line in lines:
        num += 1
        res = Tool._reImgPatt.match(line)
        if not res:
            outstrs.append(line)
            continue
        prefix, desc, path, postfix = res.groups()
        pathType = Tool.getPathType(path)
        if pathType == 'rel':
            path = Tool.reviseRelPath(path)
            if conf.checkRel and not Tool.checkRelPath(filename, path):
                Tool.printMsg(0, 'Error', 'Image not found.', filename, num)
        elif pathType == 'abs':
            dst = os.path.join(os.path.dirname(filename), conf.assets, os.path.basename(path))
            workstack.append({'src': path, 'dst': dst, 'line': num})
            path = './' + conf.assets + '/' + os.path.basename(path)
        elif pathType == 'net':
            # 阻塞时间超长
            if conf.checkNet and not Tool.checkNetPath(path):
                Tool.printMsg(0, 'Error', 'Invalid URL(%s)' % (path,), filename, num)
        else:
            Tool.printMsg(0, 'warn', 'Invalid or unexperted image path.', filename, num)
        outstrs.append('%s![%s](%s)%s\n' % (prefix, desc, path, postfix))
    # 对于存在绝对路径的md文件，如果有任意一个文件拷贝失败，就不改变源文件内容
    for each in workstack:
        if not os.path.exists(os.path.dirname(each['dst'])):
            os.mkdir(os.path.dirname(each['dst']))
        if not os.path.isfile(each['src']):
            Tool.printMsg(0, 'Error', 'Source Image not found.', filename, each['line'])
            print('[Warn]: The file(%s) is not processed.' % filename)
            return
        if conf.logInfo:  # 是否打印这个数据
            Tool.printMsg(1, 'info', 'Copying Image...', each['src'], each['dst'])
        if not os.path.exists(each['dst']):
            shutil.copyfile(each['src'], each['dst'])
    with open(filename, 'w', encoding='utf-8') as fw:
        fw.write(''.join(outstrs))


# 消费者程序
def runner():
    while not filequeue.empty():
        lock.acquire()
        filename = filequeue.get()
        lock.release()
        inspectFile(filename)


# 消费者
class LintThread(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        runner()


# 处理输入参数
def handleArgv():
    try:
        opts, _ = getopt.getopt(sys.argv[1:], "d:f:a:i:m:oclhv", [])
    except getopt.GetoptError as e:
        print('[Error]:', e)
        print(MiLint_HELP)
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-d':
            if not conf.setWorkDir(arg):
                sys.exit(2)
        elif opt == '-f':
            if not conf.setFileName(arg):
                sys.exit(2)
        elif opt == '-a':
            conf.setAssets(arg)
        elif opt == '-i':
            conf.setIgnoreDir(arg)
        elif opt == '-m':
            conf.setThreadNum(arg)
        elif opt == '-o':
            conf.checkNet = True
        elif opt == '-c':
            conf.checkRel = False
        elif opt == '-l':
            conf.logInfo = True
        elif opt == '-h':
            print(MiLint_HELP)
            sys.exit(0)
        elif opt == '-v':
            print('Version:', MiLint_Version)
            sys.exit(0)
        else:
            print('[Warn]: Unexpected argument %s.' % (opt,))
    if not conf.isParamNormal():
        sys.exit(2)
    pass


# 多线程的调度方案
def multiScheduler():
    threads = []
    for _ in range(conf.threadNum):
        lthread = LintThread()
        lthread.start()
        threads.append(lthread)
    runner()
    for each in threads:
        each.join()
    pass


if __name__ == '__main__':
    time_start = time.time()
    handleArgv()
    if len(conf.workdir) > len(conf.filename):
        # 工作区是文件夹
        findAllMarkdownFile(conf.workdir)
        if conf.useSingle:
            while not filequeue.empty():
                inspectFile(filequeue.get())
        else:
            multiScheduler()
    else:
        inspectFile(conf.filename)
    time_cost = time.time() - time_start
    print('=== MiLint work finished, cost %.4fs ===' % (time_cost,))
    pass
