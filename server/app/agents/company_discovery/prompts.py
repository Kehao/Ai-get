"""包内提示词模板的加载与渲染。

模板随包走（`prompts/*.md`），所以**换台机器、换个宿主项目都不必再带一份提示词**。
读一次缓存住，与 `spec` 同样的理由：不重复读盘。
"""

from __future__ import annotations

from pathlib import Path
from string import Template

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

_cache: dict[str, str] = {}


class PromptError(RuntimeError):
    """模板缺失或占位符不匹配。属于包装损坏，不降级——宁可起不来也不发一份残缺提示词。"""


def render(name: str, **values: object) -> str:
    """读模板并替换占位符。

    ⚠️ 占位符对不上会**抛错而不是留个 `$foo` 在提示词里**：模型看到未替换的
    占位符会照猫画虎地把 `$foo` 当字段名输出，错误要到很下游才被发现。
    """
    text = _read(name)
    try:
        return Template(text).substitute(**values)
    except KeyError as error:
        available = ", ".join(_placeholders(text)) or "（无）"
        raise PromptError(
            f"{name} 缺少占位符 {error}；模板里用到的是：{available}"
        ) from error


def reset_cache() -> None:
    """丢弃已读入的模板（改了 `prompts/` 下的文件又不重启时用）。"""
    _cache.clear()


def _read(name: str) -> str:
    cached = _cache.get(name)
    if cached is not None:
        return cached
    path = _PROMPTS_DIR / name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise PromptError(f"提示词模板读取失败：{path}（{error}）") from error
    _cache[name] = text
    return text


def _placeholders(text: str) -> list[str]:
    """列出模板里用到的占位符名，供报错时显示。"""
    found = {
        named or braced
        for named, braced, _escaped, _invalid in Template.pattern.findall(text)
        if named or braced
    }
    return sorted(found)


if __name__ == "__main__":
    # 自检：不联网（`python -m discovery_agent.prompts`）。
    assert render(
        "extract.user.md", entity="公司", profile="P", documents="D", found_names="（暂无）"
    ).count("D") == 1
    assert "$" not in render("deepdive.user.md", entity="公司", entity_name="甲", profile="P", materials="M")

    try:
        render("extract.user.md", entity="公司")  # 少给 profile / documents
    except PromptError as error:
        assert "profile" in str(error) or "documents" in str(error), error
    else:
        raise AssertionError("缺占位符时应当抛 PromptError")

    try:
        _read("不存在的模板.md")
    except PromptError:
        pass
    else:
        raise AssertionError("模板缺失时应当抛 PromptError")

    print("prompts 自检通过（4 个模板可渲染）")
