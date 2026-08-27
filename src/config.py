"""全局配置加载。

从环境变量与 .env 文件读取；AGICTO_API_KEY 为必填项，缺失时
pydantic 抛 ValidationError 使启动停止，杜绝在无密钥状态下空跑。
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置。字段名默认转大写作为环境变量名。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 大模型渠道
    agicto_api_key: str = Field(..., description="AGICTO API Key, 必填")
    llm_base_url: str = "https://api.agicto.cn/v1/"

    # 各模型 id, 抽配置项便于切换
    llm_model_chat: str = "deepseek-v4-flash"
    llm_model_vision: str = "deepseek-v4-flash-vision-exp"
    llm_model_embedding: str = "text-embedding-3-small"

    # Obsidian vault
    obsidian_vault: str = r"C:\Users\Yilia\Documents\Obsidian Vault"

    # 嵌入维度
    embedding_dim: int = 1536

    # 去重语义相似度阈值
    dedup_similarity_threshold: float = 0.92

    # RAG 检索: 低于此余弦相似度的召回视为不相关, 直接返回"未找到"
    rag_min_similarity: float = 0.35
    # RAG 检索召回片段数
    rag_top_k: int = 5

    # 主题聚类: 笔记向量余弦相似度 >= 此值归入同主题
    cluster_similarity_threshold: float = 0.55
    # 形成主题分组的最少笔记数, 少于此数视为单篇独立
    cluster_min_size: int = 2

    # 薄弱主题判定: 掌握度低于此值视为薄弱
    weak_mastery_threshold: float = 0.6

    # 截图快捷键
    screenshot_hotkey: str = "ctrl+shift+s"

    # 运行时数据目录
    data_dir: str = "data"

    # FastAPI 服务监听
    api_host: str = "127.0.0.1"
    api_port: int = 8765

    @property
    def vault_path(self) -> Path:
        """vault 路径, 用 pathlib 处理含空格的路径。"""
        return Path(self.obsidian_vault)

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def sqlite_path(self) -> Path:
        """统一 SQLite 路径: 块级向量 + 笔记元数据 + 卡片库 / 掌握度。"""
        return self.data_path / "app.db"

    @property
    def rag_vault_root(self) -> Path:
        """项目在 vault 内的运行时根目录(写 MOC / 截图笔记)。

        用不带点的目录名(obsidian-rag)而非 .obsidian-rag: Obsidian 默认忽略点开头
        路径, 不带点才能在文件管理器 / 搜索 / 图谱中自动显示。
        """
        return self.vault_path / "obsidian-rag"

    @property
    def moc_path(self) -> Path:
        """MOC 索引页写回 vault 的独立子目录, 不动原笔记。"""
        return self.rag_vault_root / "moc"

    @property
    def screenshot_vault_path(self) -> Path:
        """截图原图与 .md 笔记写回 vault 的独立子目录, Obsidian 可见, 不动原笔记。"""
        return self.rag_vault_root / "screenshots"


_settings: Settings | None = None


def get_settings() -> Settings:
    """单例配置。缺失 AGICTO_API_KEY 时实例化抛错, 启动停止。"""
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings


def should_ignore_path(path: Path) -> bool:
    """vault 路径是否应被索引忽略。

    点开头目录(.obsidian 等) + 运行时子目录 obsidian-rag(moc/screenshots)。
    watcher 增量与 cli 全量共用同一份忽略规则, 避免运行时目录被当普通笔记
    重复索引(否则截图嵌图会被再 OCR 一次, MOC 导航页也会污染检索)。
    """
    s = get_settings()
    try:
        rel_parts = path.relative_to(s.vault_path).parts
    except ValueError:
        return False
    if any(part.startswith(".") for part in rel_parts):
        return True
    return bool(rel_parts) and rel_parts[0] == s.rag_vault_root.name
