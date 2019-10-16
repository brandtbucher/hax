import setuptools  # type: ignore

import hax


with open("README.md") as readme:
    long_description = readme.read()


setuptools.setup(
    author="Brandt Bucher",
    author_email="brandtbucher@gmail.com",
    description="Write compiled bytecode inline with standard Python syntax.",
    keywords="bytecode",
    license="MIT",
    long_description=long_description,
    long_description_content_type="text/markdown",
    name="hax",
    py_modules=["hax"],
    url="https://github.com/brandtbucher/hax",
    version=hax.__version__,
)
