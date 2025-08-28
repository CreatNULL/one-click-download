# one-click-download

- 需要科学上网，不然访问GitHub会失败的。
- 不要双击运。
- 对于项目文件较大的，可能会看上去像是卡死了不执行。
- 检测更新的逻辑仅仅是判断是否存在对应版本的目录，对于latest一直都是最新
- 执行多个下载的时候，访问之间，我也没加延迟，会不会出问题不晓得，反正试过一口气下载38个项目，没封我代理IP。
- 之前想着打包成exe，但是打包后就出问题，可能是路径的问题，设置不隐藏终端，就可以，设置隐藏终端一执行就报错。
- 可能会有其他的bug

## 待改进的bug
暂无

## 一、介绍：
爱搜集，保存到本地(●'◡'●)，每次软件更新一个个访问麻烦，让ai帮忙写一个哈哈

  ## 二、预览：

<img width="1750" height="875" alt="image" src="https://github.com/user-attachments/assets/5a03caa8-54c5-4cd4-bfd4-1ddf6d8456d7" />

<img width="1750" height="875" alt="image" src="https://github.com/user-attachments/assets/499c70c4-b52a-4cc1-aee2-df64749167f3" />


## 三、新增项目
<img width="1750" height="875" alt="image" src="https://github.com/user-attachments/assets/a3c833c5-9f32-4ea8-914e-b5f3ccfab37e" />


## 四、执行多选
<img width="1750" height="875" alt="image" src="https://github.com/user-attachments/assets/f6b926e8-c672-4859-8cf3-1c8ef9569c3f" />


### (三)、输出目录
版本/source/xxx.zip 对应主页的源码zip下载，版本/xxx.tat.gz 等对应release页面下的文件
<img width="462" height="241" alt="image" src="https://github.com/user-attachments/assets/91d3cee4-8c84-4663-aad8-b0fa413fe68d" />

对于仅仅只有源码的：
- 首次下载，下载后，设置文件的修改时间为commit时间，然后后续访问对比文件的修改时间，和commit提交时间，新的时间 > 文件的修改时间，判定版本更新，
- 放置历史版本到 history目录以时间戳为目录
<img width="531" height="266" alt="image" src="https://github.com/user-attachments/assets/a22b36b2-033e-4a96-909b-58834ed09ed3" />

说明.md
- 记录了版本信息
- 项目的about
- 文件名称，文件hash值，如果项目release中存在
- 项目release那记录的版本变化

### (四)、完整性校验:
如果项目存在sha256：
- 本地文件不存在，直接下载
- 项目存在hash值，判断是否匹配，存在直接跳过下载，hash值不匹配，则重新下载

如果项目不存在hash
- 直接下载
<img width="1652" height="719" alt="image" src="https://github.com/user-attachments/assets/e717b1e9-531e-4192-9555-e7f6af440d64" />
<img width="1002" height="592" alt="image" src="https://github.com/user-attachments/assets/b89e5499-6e4f-4db7-a457-4ef72fd31361" />


## (六)、钉钉发送通知
<img width="1750" height="875" alt="image" src="https://github.com/user-attachments/assets/55491341-2942-4f2d-a45c-7e08a72fa966" />

### 下载
<img width="1752" height="914" alt="image" src="https://github.com/user-attachments/assets/7b825102-f327-4df5-932b-be1bcf4fda12" />

### 更新
操作类型改为update，全局配置填写钉钉api
<img width="1752" height="914" alt="image" src="https://github.com/user-attachments/assets/6778a7c5-4778-4c56-b6bd-c40e27b0421f" />
<img width="483" height="822" alt="image" src="https://github.com/user-attachments/assets/0054df6b-19d1-48c8-8445-01a82d1a6a33" />


### (七)、定时执行
在这里勾选
<img width="1750" height="875" alt="image" src="https://github.com/user-attachments/assets/723931cc-4c30-47f8-bfe0-fcf4f0c5f711" />

每分钟
```
* * * * *
```
<img width="1755" height="882" alt="image" src="https://github.com/user-attachments/assets/21bf1d4a-ca20-4d52-abff-e0a92d2ae8eb" />

每5分钟
```
*/5 * * * * 
```
<img width="1715" height="914" alt="image" src="https://github.com/user-attachments/assets/540c11d6-37aa-45f3-8668-b2f9573f544e" />

每天0点
```
0 0 * * *
```
<img width="1752" height="914" alt="image" src="https://github.com/user-attachments/assets/a66133c6-779b-4fc1-ab2b-efbe7698ba78" />


### (八)、代理
没啥用的代理感觉，用的是requests的 proxies参数，它不支持带账号密码代理
勾选，保存配置，才能应用代理
<img width="1752" height="914" alt="image" src="https://github.com/user-attachments/assets/556f02c9-3d11-4cca-928f-eb7576a03115" />
<img width="1920" height="779" alt="image" src="https://github.com/user-attachments/assets/26fca0c4-e17f-4711-8e5a-3d1b32bb215f" />

## no_gui.py 命令行 版本
<img width="771" height="442" alt="image" src="https://github.com/user-attachments/assets/eef3292d-b851-4baf-bfc9-214207918a71" />

查看所有配置
```
python3 no_gui.py list
```
<img width="1418" height="802" alt="image" src="https://github.com/user-attachments/assets/5e8c6f60-ce24-4075-ac95-1119e1cc11de" />

添加\查看
```
python3 no_gui.py add
```
```
python3 no_gui.py config {global,project} show
```
<img width="964" height="596" alt="image" src="https://github.com/user-attachments/assets/eac78d39-be6e-4191-81d5-0b266a4c7025" />

获取/设置 单项
```
python3 no_gui.py config {global,project} {set,get} <key>
```
<img width="1041" height="196" alt="image" src="https://github.com/user-attachments/assets/cc74ae6b-4a1f-41c7-b35c-de7d89499e76" />

执行
```
python3 no_gui.py execute <项目>
python3 no_gui.py execute  # 执行下载所有的
```
<img width="1587" height="794" alt="image" src="https://github.com/user-attachments/assets/931bd38a-e5d1-4647-9853-9b3fc9b8fb49" />

停止所有的(正在下载的不会停止）
```
python3 no_gui.py stop
```
定时任务 (需要配置定时配置，和需要执行的项目）
```
python3 no_gui.py schedule
```
<img width="1150" height="350" alt="image" src="https://github.com/user-attachments/assets/c00cea4c-8887-4eab-8333-c1d550647bca" />


### 修复
2025年8月27日-00点11分-修复
- 代理开关没有立即生效，明明没有勾选应用代理， 还是在使用代理
- 本来打算每个项目都独立日志，结果日志文件记录没有使用单独的，实际用了同一个，干脆改为大家用同一个日志
- 修改，执行前自动保存一下配置，我自己经常忘记点击保存
- 新建项目，设置认输出路径为./output/项目名称

2025年8月27日-07点47分-修复
- 对于只有latest没有release的项目，即只有源码的项目，对于是否存在新版本，存在判断逻辑存在问题，修复： 首次下载后修改文件的修改时间为commit的时间，下次访问对比这个时间和commit时间，发生变动则下载，历史的版本移动到./history/commit时间戳/xxx.zip
- 发现线程数设置有问题。修改，改为全局配置，单个项目的线程数固定值4 ，这个设置的代表的是同时执行几个项目下载。

2025年8月27日-22点31分-修复
- 没有指定日志的时候日志文件为 ./logs/github_download.log
- 添加保存的验证逻辑（api，代理，URL格式的基本验证)
- 勾选项目后，勾选状态丢失问题

2025年8月28日-06点08分-修复
- 修复版本是否更新判断逻辑，原本只是判断是否存在对应版本的文件夹，对于 latest 版本这是有问题的。修改后判断里面的文件是否存在更新。
2025年8月28日-20点56分-修复
- 修复模块 dateutil  导入异常

