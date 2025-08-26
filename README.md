# one-click-download

- 需要科学上网，不然访问GitHub会失败的。
- 这个参数不用管他，对应requests的 verify=False/verify=True

<img width="115" height="25" alt="image" src="https://github.com/user-attachments/assets/454f06c7-6a18-4cb9-b3cc-31e6db45beb6" />

- 执行多个下载的时候，访问之间，我也没加延迟，会不会出问题不晓得，反正试过一口气下载38个项目，没封我代理IP，哈哈
- 之前想着打包成exe，但是打包后就出问题，可能是路径的问题，设置不隐藏终端，就可以，设置隐藏终端一执行就报错。
- 可能会有其他的bug

## 待改进的
对于只有latest没有release的最新版本判断逻辑存在问题。（当前判断逻辑，只要有latest文件名就认为为最新的）

## 一、介绍：
爱搜集，保存到本地(●'◡'●)，每次软件更新一个个访问麻烦，让ai帮忙写一个哈哈

  ## 二、预览：
<img width="1752" height="914" alt="image" src="https://github.com/user-attachments/assets/a2b49fe4-205a-4da8-a9e8-505c86b30916" />

## 三、新增项目
<img width="1752" height="914" alt="image" src="https://github.com/user-attachments/assets/65eee151-c86c-4ac9-a003-a86f2c33c5f3" />

## 四、执行多选
<img width="1752" height="914" alt="image" src="https://github.com/user-attachments/assets/d590ded2-34f3-4877-a8b2-47a7de285878" />

### (三)、输出目录
版本/source/xxx.zip 对应主页的源码zip下载，版本/xxx.tat.gz 等对应release页面下的文件
<img width="462" height="241" alt="image" src="https://github.com/user-attachments/assets/91d3cee4-8c84-4663-aad8-b0fa413fe68d" />

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
<img width="1752" height="914" alt="image" src="https://github.com/user-attachments/assets/f63c35b4-ddf7-436a-b41f-f349051e7b30" />

### 下载
<img width="1752" height="914" alt="image" src="https://github.com/user-attachments/assets/7b825102-f327-4df5-932b-be1bcf4fda12" />

### 更新
操作类型改为update，全局配置填写钉钉api
<img width="1752" height="914" alt="image" src="https://github.com/user-attachments/assets/6778a7c5-4778-4c56-b6bd-c40e27b0421f" />
<img width="483" height="822" alt="image" src="https://github.com/user-attachments/assets/0054df6b-19d1-48c8-8445-01a82d1a6a33" />


### (七)、定时执行
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

### 修复
2025年8月27日-00点11分-修复
- 代理开关没有立即生效，明明没有勾选应用代理， 还是在使用代理
- 日志文件记录没有使用单独的，实际用了同一个，干脆改为大家用同一个日志
- 执行前自动保存一下配置，我自己经常忘记点击保存
- 新建项目提默认输出路径




