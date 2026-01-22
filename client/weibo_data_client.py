import asyncio
import os
import logging

from fastmcp import Client
from mcp.types import TextContent
from fastmcp.client.sampling import RequestContext, SamplingMessage, SamplingParams
from openai import OpenAI
import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)



sampling_llm = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1"
)


class LLMClient:
    """大语言模型客户端，负责与LLM API进行通信"""

    def __init__(self, model_name: str, url: str, api_key: str) -> None:
        """
        初始化LLM客户端

        Args:
            model_name: 模型名称
            url: API基础URL
            api_key: API密钥
        """
        self.model_name: str = model_name
        self.url: str = url
        self.client = OpenAI(api_key=api_key, base_url=url)

    def get_response(self, messages: list[dict[str, str]]) -> str:
        """
        向LLM发送消息并获取响应

        Args:
            messages: 消息列表，每条消息包含role和content

        Returns:
            LLM的响应文本
        """
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            stream=False
        )
        return response.choices[0].message.content


class ChatSession:
    """聊天会话管理器，处理用户输入、LLM响应和资源访问"""

    def __init__(self, llm_client: LLMClient, mcp_client: Client) -> None:
        """
        初始化聊天会话

        Args:
            llm_client: LLM客户端实例
            mcp_client: MCP客户端实例，用于访问资源
        """
        self.mcp_client: Client = mcp_client
        self.llm_client: LLMClient = llm_client

    async def process_llm_response(self, llm_response: str) -> str:
        """
        处理LLM的响应，解析资源URI调用或工具调用并执行

        Args:
            llm_response: LLM返回的响应文本

        Returns:
            处理后的响应文本，包含资源数据或工具执行结果
        """
        try:
            # 检查是否为资源URI调用（以db://开头）
            if llm_response.strip().startswith('db://'):
                uri = llm_response.strip()
                try:
                    # 执行资源读取
                    resource_data = await self.mcp_client.read_resource(uri=uri)
                    logger.debug("【Resource】%s", resource_data)
                    return f"Resource data: {resource_data}"
                except Exception as e:
                    error_msg = f"Error reading resource: {str(e)}"
                    logger.error(error_msg)
                    return error_msg
            else:
                # 尝试解析为JSON工具调用（保留兼容性）
                if llm_response.startswith('```json'):
                    llm_response = llm_response.strip('```json').strip('```').strip()
                try:
                    tool_call = json.loads(llm_response)
                    if "tool" in tool_call and "arguments" in tool_call:
                        # 检查工具是否可用
                        available_tools = await self.mcp_client.list_tools()
                        if any(tool.name == tool_call["tool"] for tool in available_tools):
                            try:
                                # 执行工具调用
                                tool_result = await self.mcp_client.call_tool(
                                    tool_call["tool"], tool_call["arguments"]
                                )
                                return f"Tool execution result: {tool_result}"
                            except Exception as e:
                                error_msg = f"Error executing tool: {str(e)}"
                                logging.error(error_msg)
                                return error_msg
                        return f"Tool not found: {tool_call['tool']}"
                except json.JSONDecodeError:
                    pass
                # 如果不是JSON格式或工具调用，直接返回原始响应
                return llm_response
        except Exception as e:
            error_msg = f"Error processing LLM response: {str(e)}"
            logging.error(error_msg)
            return error_msg

    async def start(self, system_message: str) -> None:
        """
        启动聊天会话的主循环

        Args:
            system_message: 系统提示消息，指导LLM的行为
        """
        messages = [{"role": "system", "content": system_message}]
        while True:
            try:
                # 获取用户输入
                user_input = input("用户: ").strip().lower()
                if user_input in ["quit", "exit", "退出"]:
                    print('AI助手已退出')
                    break
                messages.append({"role": "user", "content": user_input})

                # 获取LLM的初始响应
                llm_response = self.llm_client.get_response(messages)
                print("助手: ", llm_response)

                # 处理可能的资源调用或工具调用
                result = await self.process_llm_response(llm_response)

                # 如果处理结果与原始响应不同，说明执行了资源调用或工具调用，需要进一步处理
                while result != llm_response:
                    messages.append({"role": "assistant", "content": llm_response})
                    messages.append({"role": "system", "content": f"这是查询到的数据，请基于这些数据回答用户问题：\n{result}"})

                    # 将资源数据或工具执行结果发送回LLM获取新响应
                    llm_response = self.llm_client.get_response(messages)
                    result = await self.process_llm_response(llm_response)
                    print("助手: ", llm_response)

                messages.append({"role": "assistant", "content": llm_response})

            except KeyboardInterrupt:
                print('AI助手已退出')
                break


async def sampling_func(messages, params, ctx):
    logger.info("### sampling_handler CALLED ###")

    # MCP SamplingMessage → OpenAI messages
    llm_messages = []

    if params.systemPrompt:
        llm_messages.append({
            "role": "system",
            "content": params.systemPrompt
        })

    for m in messages:
        llm_messages.append({
            "role": m.role,
            "content": m.content.text
        })

    logger.info("sampling messages: %s", llm_messages)

    try:
        response = sampling_llm.chat.completions.create(
            model="deepseek-chat",
            messages=llm_messages,
            stream=False
        )
        text = response.choices[0].message.content
        logger.info("sampling result: %s", text)

        # 可以直接返回文本
        return text

    except Exception as e:
        logger.exception("sampling failed")
        return "未知"

async def main():
    """主函数，初始化客户端并启动聊天会话"""
    async with Client("http://127.0.0.1:8002/mcp", sampling_handler=sampling_func) as mcp_client:
        # 初始化LLM客户端，使用通义千问模型
        llm_client = LLMClient(
            model_name='qwen-plus-latest',
            api_key=os.getenv('DASHSCOPE_API_KEY'),
            url='https://dashscope.aliyuncs.com/compatible-mode/v1'
        )

        # 获取可用资源模板
        resource_templates = await mcp_client.list_resource_templates()
        template_dicts = [template.__dict__ for template in resource_templates]
        resources_description = json.dumps(template_dicts, ensure_ascii=False)

        # 系统提示，指导LLM如何使用资源模板和返回响应
        system_message = f'''
                你是一个智能助手，能够访问多种数据资源。严格遵循以下协议返回响应：

                可用资源模板：{resources_description}

                响应规则：
                1、当用户询问需要查询数据时，判断是否需要调用资源模板：
                 - 如果需要查询数据，返回对应的资源URI
                 - 如果是普通对话，直接回答用户问题

                2、资源调用格式：
                 - 返回纯净的URI字符串，不包含任何其他内容
                 - URI格式必须严格按照资源模板定义
                 - 根据用户需求填入合适的参数值
                 
                3、URI参数说明：
                 - date: 日期参数，格式如0101表示1月1日
                 - limit: 限制返回数据条数
                 - 其他参数根据资源模板定义填入

                4、非数据查询的响应：
                 - 对于普通对话，直接给出自然语言回答
                 - 不需要调用资源时，不要返回URI

                5、收到资源数据后：
                 - 将数据转化为用户友好的格式
                 - 突出显示关键信息
                 - 保持回复简洁清晰
                 - 根据用户问题提供相关分析
                '''

        # 启动聊天会话
        chat_session = ChatSession(llm_client=llm_client, mcp_client=mcp_client)
        await chat_session.start(system_message=system_message)


if __name__ == "__main__":
    asyncio.run(main())
