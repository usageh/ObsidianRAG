"""FastAPI 应用: RAG 问答路由 + 静态前端托管。

/api/ask 路由先于静态挂载注册, 优先匹配; 前端根路径 "/" 返回问答页。
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.clustering import merge_view
from src.graph import build_graph
from src.rag.generate import generate_answer
from src.rag.retrieve import retrieve
from src import reinforcement

app = FastAPI(title="Obsidian RAG", version="0.1.0")


class AskRequest(BaseModel):
    """问答请求体。"""

    question: str = Field(..., description="用户问题")
    k: int | None = Field(default=None, description="召回片段数, 留空用配置默认")


@app.get("/api/health")
def health() -> dict:
    """健康检查。"""
    return {"status": "ok"}


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    """问答接口: 问题 → 回答 + 来源 + 同主题分组视图。

    返回 {"answer","sources":[...],"groups":[...]}。无相关内容时 answer 为
    固定提示、sources/groups 为空。
    """
    hits = retrieve(req.question, k=req.k)
    result = generate_answer(req.question, hits)
    return {**result, "groups": merge_view(hits)}


# ---------- 巩固: 间隔重复抽问 ----------


class GenerateCardsRequest(BaseModel):
    """生成问答对卡片请求。"""

    note_path: str = Field(..., description="源笔记相对路径")
    topic_id: str | None = Field(default="", description="主题 id, 留空不归属")
    n: int = Field(default=3, description="生成卡片数")


class ReviewRequest(BaseModel):
    """卡片复习评级请求。"""

    card_id: str
    rating: int = Field(..., description="1=Again 2=Hard 3=Good 4=Easy")


@app.post("/api/cards/generate")
def cards_generate(req: GenerateCardsRequest) -> dict:
    """基于笔记生成问答对卡片。"""
    cards = reinforcement.generate_cards(req.note_path, topic_id=req.topic_id or "", n=req.n)
    return {"cards": cards, "count": len(cards)}


@app.get("/api/cards/due")
def cards_due() -> dict:
    """到期待复习卡片列表。"""
    return {"cards": reinforcement.due_cards()}


@app.post("/api/cards/review")
def cards_review(req: ReviewRequest) -> dict:
    """对一张卡片评级, 更新 FSRS 调度与主题掌握度。"""
    return reinforcement.review_card(req.card_id, req.rating)


# ---------- 巩固: AI 主动测验 ----------


class QuizGenerateRequest(BaseModel):
    topic_id: str


class QuizSubmitRequest(BaseModel):
    topic_id: str
    question: str
    reference_answer: str
    rating: int = Field(..., description="1=Again 2=Hard 3=Good 4=Easy")


@app.get("/api/quiz/weak")
def quiz_weak() -> dict:
    """薄弱主题列表。"""
    return {"topics": reinforcement.weak_topics()}


@app.post("/api/quiz/generate")
def quiz_generate(req: QuizGenerateRequest) -> dict:
    """针对薄弱主题生成一道测验题。"""
    return reinforcement.generate_quiz(req.topic_id)


@app.post("/api/quiz/submit")
def quiz_submit(req: QuizSubmitRequest) -> dict:
    """用户作答后: 测验题建卡并按评级复习, 更新掌握度。"""
    return reinforcement.submit_quiz(
        req.topic_id, req.question, req.reference_answer, req.rating
    )


# ---------- 知识图谱 ----------


@app.get("/api/graph")
def graph() -> dict:
    """知识图谱: 节点=笔记, 边=显式 wikilink + 隐式同主题。"""
    return build_graph()


# 静态前端: 项目根 frontend/ 目录, html=True 使 "/" 自动返回 index.html
_frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if _frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
