# ubuntu中selenium+chrome截图时中文显示成方框问题的解决方法

## 解决方法：

### 1.下载任意一种中文字体，或者直接从windows系统字体文件夹(C:\Windows\Fonts)中选择一种，比如宋体simsun.ttc

### 2.将该字体文件放入/usr/share/fonts/路径下

### 3.修改权限

```
sudo chmod 644 /usr/share/fonts/simsun.ttc
```

### 4.在终端依次执行以下命令，使字体生效

```
sudo mkfontscale
sudo mkfontdir
sudo fc-cache -fv
```

### 在执行上述命令的过程中，如果出现command not found，则需要先执行以下命令进行安装：

```
# 使mkfontscale和mkfontdir命令正常运行
sudo apt-get install ttf-mscorefonts-installer
# 使fc-cache命令正常运行
sudo apt-get install fontconfig
```