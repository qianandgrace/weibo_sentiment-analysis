weibo data analysis system
# 亮点1
利用sampling func，服务端获取到微博数据后，返回到客户端，利用客户端的大模型给数据打上标签，并返还给服务端
![sample func](assets/29.png "")

# 亮点2
利用qwen作为全局大模型，deepseek作为情感分析模型，两大模型协同工作
