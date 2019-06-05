# MiLint

> A markdown inspection tool for checking whether the image paths in the file are available and addressable.
>
> 该工具用于检查MarkDown文件中所引用的图片的路径是否为相对路径或网络路径；



## 处理逻辑


- 如果路径为**绝对路径**，程序会将绝对路径的图片保存到指定目录中，默认为文件所在目录的`assets`文件夹；
- 如果路径为**相对路径**，程序会检查该路径的图片是否存在，是否可以访问；
- 如果路径为**网络路径**，程序会检查该Url是否可以访问。