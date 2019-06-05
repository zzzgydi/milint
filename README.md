# MiLint

> A markdown inspection tool for checking whether the image paths in the file are available and addressable.
>
> 该工具用于检查MarkDown文件中所引用的图片的路径是否有效和可访问；



## 处理逻辑


- 如果路径为**绝对路径**，程序会将绝对路径的图片保存到指定目录中，默认为文件所在目录的`assets`文件夹；
- 如果路径为**相对路径**，程序会检查该路径的图片是否存在，是否可以访问；
- 如果路径为**网络路径**，程序会检查该Url是否可以访问。



## 参数
```
-d <dirname>          # 设置检查的文件夹
-f <filename>         # 设置检查单一文件
-a <assets>           # 设置存放的文件夹名称，默认'assets'文件夹
-i <dirs>             # 忽略某文件夹，仅在检查文件夹状态下有效，用'!'隔开多个
-m <thread num>       # 开启多线程处理，输入线程数，不合理的数将使用默认的值
-o open net check     # 开启网络路径图片有效性检查，默认不开启
-c close rel check    # 关闭相对路径图片有效性检查，默认开启
-l open info log      # 开启Info级别的提示，默认关闭
-h Help               # 查看帮助
-v Version            # 查看版本	
```