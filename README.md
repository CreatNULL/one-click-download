# one-click-download

- 需要科学上网，不然访问GitHub会失败的。
- 这个参数不用管他，对应requests的 verify=False/verify=True

<img width="207" height="38" alt="image" src="https://github.com/user-attachments/assets/a342c2c0-b20d-4172-8d18-90a51462cd91" />

- 单个访问直接我也没加延迟，会不会出问题不晓得，反正试过一口气下载所有的，没封我代理IP，哈哈
- 之前想着打包成exe，但是打包后就出问题，可能是路径的问题，设置不隐藏终端，就可以，设置隐藏终端一执行就报错。
- 可能会有其他的bug

## 一、介绍：
爱搜集，保存到本地(●'◡'●)，每次软件更新一个个访问麻烦，让ai帮忙写一个哈哈

## 二、预览：
<img width="1752" height="914" alt="image" src="https://github.com/user-attachments/assets/4c3c4d87-d05f-42d0-8346-65373b0ae460" />

## 三、新增项目
<img width="1752" height="914" alt="image" src="https://github.com/user-attachments/assets/03e01625-c29d-4dd8-b29d-fe38ea248bc5" />

## 四、执行多选
<img width="1752" height="914" alt="image" src="https://github.com/user-attachments/assets/7bc3c4cb-b8ed-406b-9ab5-65e4bb2adf91" />

<img width="1752" height="914" alt="image" src="https://github.com/user-attachments/assets/8825fc6a-6478-4d7c-bb40-514edf74abf1" />


### (三)、输出目录
版本/source/xxx.zip 对应主页的源码zip下载，版本/xxx.tat.gz 等对应release页面下的文件
<img width="819" height="552" alt="image" src="https://github.com/user-attachments/assets/4f950b17-e68b-4637-bc93-6df66a49d85a" />

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

<img width="800" height="400" alt="image" src="https://github.com/user-attachments/assets/7028f835-3da7-4193-a479-b5fd9c7f13e9" />

<img width="800" height="492" alt="image" src="https://github.com/user-attachments/assets/4024bd52-e37b-467a-a8b1-d5b3cc1f6cd8" />

## (六)、钉钉发送通知
<img width="1752" height="914" alt="image" src="https://github.com/user-attachments/assets/3e325174-e2a3-4e0e-8fdd-dbf8908165ac" />

### 下载
<img width="1752" height="914" alt="image" src="https://github.com/user-attachments/assets/df529a3c-515a-4d27-9db8-14dbaf35b049" />

### 更新
操作类型改为update，全局配置填写钉钉api
<img width="1750" height="875" alt="image" src="https://github.com/user-attachments/assets/19c88e35-0318-4ccd-acf1-cc1bf45368e7" />

<img width="483" height="822" alt="image" src="https://github.com/user-attachments/assets/bb5f9e1c-3085-4e50-8cd2-ce172ea70d23" />

### (七)、定时执行
每分钟
```
* * * * *
```
<img width="1752" height="914" alt="image" src="https://github.com/user-attachments/assets/34924414-5722-43aa-a0a5-e916540ebc49" />


每5分钟
```
*/5 * * * * 
```
<img width="1715" height="914" alt="image" src="https://github.com/user-attachments/assets/b81fe342-8a3a-42a8-9d8b-69e088ec9a8e" />


每天0点
```
0 0 * * *
```
<img width="1752" height="914" alt="image" src="https://github.com/user-attachments/assets/656b2a83-6834-410f-8a9f-406f57a47609" />

### (八)、代理
没啥用的代理感觉，用的是requests的 proxies参数，它不支持带账号密码代理
<img width="1435" height="772" alt="image" src="https://github.com/user-attachments/assets/2ae0e778-6e4e-444a-b164-e0aa671a74f4" />

勾选，保存配置，才能应用代理
<img width="1270" height="835" alt="image" src="https://github.com/user-attachments/assets/f03186f9-039e-44a1-832e-fab6a1c8d3b3" />


