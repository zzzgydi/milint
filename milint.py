# -*- coding: utf-8 -*-
import re, os, shutil
from urllib.request import urlopen
'''
判断逻辑：
    1. 获取文档中的图片路径
    2. 判断路径的类型
        2.1 如果 相对路径：将\\ 的分割符转成//或/的分隔符。。
        2.2 如果 绝对路径：1.计算原始的路径，生成目标路径；2.将图片拷贝至目标路径
        2.3 如果 网络路径：检查图片是否能访问
'''

c_assets = 'assets'  # 默认将md中的图片放在md目录下的assets文件夹
c_checknet = True  # 是否检查网络路径的图片
c_checkrel = True  # 是否检查相对路径的图片
c_recursion = True  # 是否开启递归遍历文件夹

# old: ^(\.{1,2}[\\/]{1,2})*([^\.\\/:]+[\\/]{1,2})*[^\.:]*(\.[^\.:]+)?
# 相对路径
relPath = re.compile(
    r"^(\.{1,2}|(\.{1,2}[\\/]{1,2})*)([^\.\\/:]+[\\/]{1,2})*[^\.:]*(\.[^\.:]+)?"
)
# win绝对路径 能匹配类似 C://../这种
absPath = re.compile(r"^([A-Z]:)([\\/]{1,2}[^\\/]*)*", re.I)
# Linux绝对路径 能匹配 /../.. 但不能匹配 ../
absLPath = re.compile(r"^([\\/]{1,2}[^\\/]*)*")
# 网络路径
netPath = re.compile(r"[a-zA-z]+://[^\s]*")
# 匹配md中的图片语法
imgPatt = re.compile(r"!\[(.*?)\]\((.+)\)")
# 用于切割路径的正则
splitRe = re.compile(r"[\\/]{1,2}")


# 判断路径类型 有相对路径、绝对路径、网络路径
def getPathType(path):
    reList = [{
        're': absPath,
        'return': 'abs'
    }, {
        're': relPath,
        'return': 'rel'
    }, {
        're': absLPath,
        'return': 'abs'
    }, {
        're': netPath,
        'return': 'net'
    }]
    for each in reList:
        tmp = each['re'].match(path)
        if tmp and tmp.group(0) == path:
            return each['return']
    return None


# 将相对路径中的 反斜杠 转成斜杆
def reviseRelPath(path):
    return path.replace('\\', '/')


# 递归查找某目录下的所有md文件
def findAllMarkDown(root):
    mdList = []
    mdRe = re.compile(r'.*?\.md$')

    def recurPath(rpath):
        dirs = os.listdir(rpath)
        for i in dirs:
            tmp = os.path.join(rpath, i)
            if os.path.isdir(tmp):
                recurPath(tmp)
            elif os.path.isfile(tmp) and mdRe.match(i):
                mdList.append(tmp)

    recurPath(root)
    return mdList


# 用于检查相对路径下的文件是否可以访问，传入参数，md文件的路径（绝对），图片路径（相对）
def checkRelPath(filepath, imgPath):
    if os.path.isfile(filepath):
        filepath = os.path.dirname(filepath)
    for i in splitRe.split(imgPath):
        if i == '..':
            filepath = os.path.dirname(filepath)
        elif i == '.':
            continue
        else:
            filepath = os.path.join(filepath, i)
    return os.path.exists(filepath)


# 用于检查网络路径的图片是否可用
def checkNetPath(path):
    print('Requring URL:', path)
    if urlopen(path).getcode() != 200:
        return False
    return True


# 打印错误信息
def printErrorMsg(level, msg, filename, line):
    print("[%s]: %s" % (level.capitalize(), msg))
    print("  File:", filename)
    print("  Line:", line)


# 对每个文件进行处理
def handleFile(filename):
    outputs, workstack, num = [], [], 0
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for line in lines:
            num += 1
            res = imgPatt.match(line)
            if not res:
                outputs.append(line)
                continue
            desc, path = res.group(1), res.group(2)
            ptype = getPathType(path)
            if ptype == 'rel':
                path = reviseRelPath(path)
                if c_checkrel and not checkRelPath(filename, path):
                    printErrorMsg('error', 'Image not found.', filename, num)
            elif ptype == 'abs':
                dst = os.path.join(os.path.dirname(filename), c_assets,
                                   os.path.basename(path))
                workstack.append({'src': path, 'dst': dst})
                path = './' + c_assets + '/' + os.path.basename(path)
            elif ptype == 'net':
                if c_checknet and not checkNetPath(path):
                    printErrorMsg('Error', 'Invalid URL.', filename, num)
                else:
                    print('Passing', path)
            else:
                printErrorMsg('Warn', 'Invalid or unexperted image path.',
                              filename, num)
            outputs.append('![%s](%s)\n' % (desc, path))
        # 开始移动图片
        for each in workstack:
            if not os.path.exists(os.path.dirname(each['dst'])):
                os.mkdir(os.path.dirname(each['dst']))
            print('Copying Image: src[%s] dst[%s]' %
                  (each['src'], each['dst']))
            if not os.path.exists(each['dst']):
                shutil.copyfile(each['src'], each['dst'])
        outstr = ''
        for li in outputs:
            outstr += li
        with open(filename, 'w', encoding='utf-8') as fw:
            fw.write(outstr)
    except UnicodeDecodeError:
        print('Error: Please use utf-8...')
    except UnicodeEncodeError:
        print('Error: Please use utf-8...')
    except Exception as e:
        print(e)
    pass


def help():
    print('''Usage:
  -d <dirname>          # 设置检查的文件夹
  -n <T/F>              # 是否开启网络路径图片有效性检查，默认不开启
  -r <T/F>              # 是否开启相对路径图片有效性检查，默认开启
  -D Document           # 查看程序描述
  -f Forbid recursion   # 关闭递归遍历文件夹
  -h Help               # 查看帮助''')
    pass


def doc():
    print('''Description:
* 程序检索目标文件夹下的所有md文件，对每个文件，检查插入的图片路径是否合理
  1. 将绝对路径的写法改成在当前目录的assets文件夹下
  2. 将相对路径的反斜杠转成斜杆
  3. 检查网络路径的图片是否能访问''')


# 主函数
def mainRun(root):
    fileList = findAllMarkDown(root)
    for eachfile in fileList:
        handleFile(eachfile)
    pass


# 处理参数
def handleParams(argv):
    pass


if __name__ == "__main__":
    help()
    print(os.path.abspath('./Test'))
    # mainRun('D:\Test')
