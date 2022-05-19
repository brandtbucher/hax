from setuptools import setup

from hax import __version__ as version


with open("README.md", encoding="utf-8") as readme:
    _LONG_DESCRIPTION = readme.read()


setup(
    author="Brandt Bucher",
    author_email="brandtbucher@gmail.com",
    description="Write compiled bytecode inline with standard Python syntax.",
    keywords="bytecode",
    license="MIT",
    long_description=_LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    name="hax",
    packages=["hax"],
    url="https://github.com/brandtbucher/hax",
    version=version,
)
