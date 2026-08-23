from setuptools import setup, find_packages

setup(
    name="soul-engine",
    version="1.1.1",
    description="Epistemic Bio-Homeostatic Identity & Memory Kernel for AI Agents with Model Context Protocol (MCP) Interface",
    long_description=open("README.md", encoding="utf-8").read(),
    author="Azhonaras (Navid Badami)",
    author_email="nbada@users.noreply.github.com",
    py_modules=["soul_kernel", "soul_mcp_server", "soul_review", "install", "soul_host"],
    install_requires=[],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "ruff>=0.1.0",
            "mypy>=1.0.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "soul-mcp=soul_mcp_server:main",
            "soul-install=install:main",
            "soul-host=soul_host:main",
        ],
    },
    python_requires=">=3.9",
    data_files=[
        ("share/soul-engine/skills/soul-seal", ["skills/soul-seal/SKILL.md"]),
    ],
)
