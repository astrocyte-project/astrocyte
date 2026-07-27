# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/astrocyte-project/astrocyte/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                   |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|--------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/astrocyte/\_\_init\_\_.py          |        4 |        0 |        0 |        0 |    100% |           |
| src/astrocyte/agents/\_\_init\_\_.py   |        0 |        0 |        0 |        0 |    100% |           |
| src/astrocyte/agents/coach.py          |       85 |       33 |       20 |        3 |     54% |59-64, 68, 72-75, 84-91, 105, 107, 141-176, 196-\>198 |
| src/astrocyte/api/\_\_init\_\_.py      |        2 |        0 |        0 |        0 |    100% |           |
| src/astrocyte/api/\_\_main\_\_.py      |        5 |        5 |        2 |        0 |      0% |      3-16 |
| src/astrocyte/api/app.py               |       45 |        1 |        8 |        1 |     96% |        45 |
| src/astrocyte/api/approvals.py         |       46 |        1 |       10 |        1 |     96% |        31 |
| src/astrocyte/cli/\_\_init\_\_.py      |        0 |        0 |        0 |        0 |    100% |           |
| src/astrocyte/cli/main.py              |       95 |       43 |       20 |        4 |     56% |61-65, 75-76, 97-116, 120-140, 149, 151, 158 |
| src/astrocyte/core/\_\_init\_\_.py     |        0 |        0 |        0 |        0 |    100% |           |
| src/astrocyte/core/config.py           |       17 |        0 |        0 |        0 |    100% |           |
| src/astrocyte/core/connector.py        |       17 |        0 |        0 |        0 |    100% |           |
| src/astrocyte/core/llm/\_\_init\_\_.py |        2 |        0 |        0 |        0 |    100% |           |
| src/astrocyte/core/llm/router.py       |       66 |        0 |        8 |        0 |    100% |           |
| src/astrocyte/core/policy.py           |      228 |        4 |       48 |        4 |     97% |104, 187, 394, 396 |
| src/astrocyte/ha/\_\_init\_\_.py       |        3 |        0 |        0 |        0 |    100% |           |
| src/astrocyte/ha/client.py             |       74 |        3 |       16 |        2 |     94% |62, 94, 145 |
| src/astrocyte/ha/connector.py          |       24 |        0 |        4 |        0 |    100% |           |
| src/astrocyte/ha/mcp.py                |       66 |        8 |       16 |        4 |     85% |37-\>39, 40, 42, 67, 74, 81, 95, 163-164 |
| src/astrocyte/ha/status.py             |       30 |        1 |       14 |        2 |     93% |28-\>30, 44 |
| src/astrocyte/mcp/\_\_init\_\_.py      |        0 |        0 |        0 |        0 |    100% |           |
| src/astrocyte/mcp/server.py            |       20 |        0 |        2 |        0 |    100% |           |
| src/astrocyte/rvc/\_\_init\_\_.py      |        3 |        0 |        0 |        0 |    100% |           |
| src/astrocyte/rvc/\_\_main\_\_.py      |        9 |        9 |        0 |        0 |      0% |      3-29 |
| src/astrocyte/rvc/analysis.py          |      208 |        2 |       60 |        4 |     98% |115, 171-\>173, 322, 358-\>360 |
| src/astrocyte/rvc/bridge.py            |      208 |       17 |       72 |       11 |     89% |118, 162-\>166, 183, 190, 214, 226, 308, 311, 315, 329-\>328, 379, 398, 403-416 |
| src/astrocyte/rvc/decoder.py           |      104 |        9 |       44 |        7 |     88% |81-\>80, 83, 92-\>94, 122, 128-130, 132, 184-190 |
| src/astrocyte/rvc/discovery.py         |      122 |        3 |       22 |        3 |     96% |99, 124, 337-\>339, 377 |
| src/astrocyte/rvc/encoder.py           |       51 |        0 |       10 |        2 |     97% |100-\>102, 102-\>104 |
| src/astrocyte/rvc/instances.py         |       87 |        3 |       20 |        3 |     94% |104-105, 132-\>131, 152 |
| src/astrocyte/rvc/spec.py              |      140 |        2 |       36 |        2 |     98% |   64, 207 |
| **TOTAL**                              | **1761** |  **144** |  **432** |   **53** | **90%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/astrocyte-project/astrocyte/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/astrocyte-project/astrocyte/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astrocyte-project/astrocyte/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/astrocyte-project/astrocyte/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fastrocyte-project%2Fastrocyte%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/astrocyte-project/astrocyte/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.