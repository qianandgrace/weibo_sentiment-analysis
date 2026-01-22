from mcp.types import TextContent
from fastmcp import Context, FastMCP
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)


# 构建 MCP Server 实例
mcp = FastMCP("weibo data mcp server",
              debug=True,
              host="0.0.0.0",
              port=8002)

# 数据库连接配置
DB_CONFIG = {
    "dbname": "postgres",
    "user": "gq210",
    "password": "123456",
    "host": "localhost",
    "port": "5432"
}

# 获取数据库连接对象
def get_db_connection():
    """创建数据库连接"""
    return psycopg2.connect(**DB_CONFIG)


@mcp.resource("db://province_info/data/{province_name}")
async def get_province_data(province_name: str) -> str:
    """中国省份（含直辖市）信息

    参数:
    province_name: 中国省份名称或直辖市，如广东省，北京市

    返回:
    以 json 格式返回某省份信息
    """
    sql = '''
            select region_code,
                   province_name,
                   capital_city,
                   area,
                   population,
                   abbreviation 
            from weibo_data.chinese_provinces 
            where province_name = '{province_name}'
    '''.format(province_name=province_name)
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            return json.dumps(list(rows), default=str)


@mcp.resource("db://movie_info/data/{movie_name}")
async def get_movie_data(movie_name: str) -> str:
    """电影信息

    参数:
    movie_name: 电影名称

    返回:
    以 json 格式返回某电影信息
    """
    sql = '''
    select movie_type, 
           main_actors, 
           region, 
           director, 
           features, 
           rating, 
           movie_name
    from weibo_data.chinese_movie_ratings
    where movie_name = '{movie_name}'
    '''.format(movie_name=movie_name)
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            return json.dumps(list(rows), default=str)


# =========================
# Weibo by date + limit
# =========================
@mcp.resource("db://weibo_data/by_date/{date}/limit/{limit}")
async def get_weibo_by_date(
    ctx: Context,
    date: str,
    limit: int
) -> str:
    """
    微博数据（按日期）

    date: mmdd example: 0101
    limit: 返回条数
    """
    sql = f"""
        select weibo_id,
               user_name,
               publish_date,
               publish_time,
               weibo_content
        from weibo_data.t_weibo_ncov
        where publish_date = '{date}'
        limit {limit}
    """
    logger.info("【SQL】%s", sql)
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()

    for row in rows:
        system_prompt = "请给出这条微博内容的情感倾向，标注为：积极 / 中性 / 消极"
        logger.info(f"【System Prompt】{system_prompt}, data: {row['weibo_content']}")
        response = await ctx.sample(
            messages=row['weibo_content'],
            system_prompt=system_prompt
        )
        logger.info("【Response】%s", response)
        row["sentiment_tag"] = response

    return json.dumps(rows, default=str)


# =========================
# Weibo by user + limit
# =========================
@mcp.resource("db://weibo_data/by_user/{weibo_user}/limit/{limit}")
async def get_weibo_by_user(
    ctx: Context,
    weibo_user: str,
    limit: int
) -> str:
    """
    某用户的微博
    """
    sql = f"""
        select weibo_id,
               user_name,
               publish_date,
               publish_time,
               weibo_content
        from weibo_data.t_weibo_ncov
        where user_name = '{weibo_user}'
        limit {limit}
    """
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()

    for row in rows:
        system_prompt = "请给出这条微博内容的情感倾向，标注为：积极 / 中性 / 消极"
        logger.info(f"【System Prompt】{system_prompt}, data: {row['weibo_content']}")
        response = await ctx.sample(
            messages=row['weibo_content'],
            system_prompt=system_prompt
        )
        logger.info("【Response】%s", response)
        row["sentiment_tag"] = response

    return json.dumps(rows, default=str)


if __name__ == "__main__":
    mcp.run("streamable-http")
