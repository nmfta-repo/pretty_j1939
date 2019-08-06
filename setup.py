import setuptools

with open("README.md", "r") as readme:
    long_description = readme.read()

setuptools.setup(
    name="pretty_j1939",
    version="0.0.1",
    author=['Ben Gardiner', 'Jeremy Daily'],
    author_email=['ben.gardiner@nmfta.org', 'jeremy-daily@utulsa.edu'],
    description="python libs and scripts for pretty-printing J1939 logs",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/nmfta-repo/pretty_j1939",
    packages=setuptools.find_packages(),
    install_requires=[
        'asteval',
        'defusedxml',
        'unidecode',
        'xlrd',
        'bitstring',
    ],
    scripts=[
        'create_j1939db-json.py',
        'pretty_j1939.py',
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
