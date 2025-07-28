<div align="center">
  <a href="https://nonebot.dev/store/plugins">
    <img src="./docs/NoneBotPlugin.svg" width="300" alt="logo">
  </a>
</div>
<div align="center">

# nonebot_plugin_jm

</div>

## 📖 介绍

下载禁漫漫画，返回 ZIP 文件

## 💿 安装

使用 nb-cli 安装插件

```shell
nb plugin install nonebot_plugin_jm
```

使用 pip 安装插件

```shell
pip install nonebot_plugin_jm
```

## 🕹️ 使用

**jm [禁漫号]** : 获得对应禁漫号的压缩包

## ⚙️ 配置

| 配置项       | 默认值 | 说明                                                       |
| ------------ | ------ | ---------------------------------------------------------- |
| jm_pwd       | None   | 解压密码，默认不设置。如需防止腾讯风控可设置字符串作为密码 |
| jm_forward   | True   | 是否转发压缩包，建议开启，直接发送可能会被风控             |
| jm_lock      | True   | 是否启用锁机制，限制单个用户的并发请求                     |
| jm_lock_size | 1      | 限制单个用户的并发请求数量，当 jm_lock 为 False 时不生效   |
