# ![freqtrade](https://raw.githubusercontent.com/freqtrade/freqtrade/develop/docs/assets/freqtrade_poweredby.svg)

[![Freqtrade CI](https://github.com/freqtrade/freqtrade/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/freqtrade/freqtrade/actions/workflows/ci.yml)
[![DOI](https://joss.theoj.org/papers/10.21105/joss.04864/status.svg)](https://doi.org/10.21105/joss.04864)
[![codecov](https://codecov.io/gh/freqtrade/freqtrade/branch/develop/graph/badge.svg?token=AD5BG3ATKI)](https://codecov.io/gh/freqtrade/freqtrade)
[![Documentation](https://readthedocs.org/projects/freqtrade/badge/)](https://www.freqtrade.io)
[![Discord Server](https://img.shields.io/badge/Freqtrade_Discord-4E4E4E?logo=discord)](https://discord.gg/p7nuUNVfP7)

Freqtrade is a free and open source crypto trading bot written in Python. It is designed to support all major exchanges and be controlled via Telegram or webUI. It contains backtesting, plotting and money management tools as well as strategy optimization by machine learning.

![freqtrade](https://raw.githubusercontent.com/freqtrade/freqtrade/develop/docs/assets/freqtrade-screenshot.png)

## 项目介绍书（Project Profile）

本项目（BTT）基于 Freqtrade，定位为“可研究、可回测、可实盘演进”的开源量化交易系统。  
项目面向策略研究者与工程开发者，提供从数据、策略、评估到执行与运维的完整闭环能力，并重点增强了 AI/FreqAI 扩展能力，便于后续接入外部模型与智能体协作流程。

### 核心优势

1. **开源透明，工程可控**
   - Python 技术栈，代码结构清晰，便于二次开发与审计。
   - 配置、策略、接口均可追踪，适合团队协作和持续迭代。

2. **交易全流程能力完整**
   - 内置数据管理、回测、超参优化、可视化、实盘/模拟交易能力。
   - 支持多交易所与多运行模式，便于从研究快速过渡到验证。

3. **AI/FreqAI 扩展友好**
   - 已提供 FreqAI 模型接口、策略回调、REST 扩展点与助手引导接口。
   - 支持分层 Prompt 圆桌配置（含启用开关、导入导出、历史回滚），便于安全迭代 AI 工作流。

4. **风险控制与安全优先**
   - 强调先回测、再模拟、后实盘的渐进流程，降低策略上线风险。
   - 支持配置化风控与状态观测，便于发现并定位异常行为。

5. **运维与开发体验完善**
   - 支持 WebUI 与 Telegram 管理，配合 API 可实现自动化运维。
   - 测试体系与文档体系完整，便于快速上手和长期维护。

### 适用场景

- 个人量化策略研究与自动化交易实践  
- 团队化策略研发与版本化管理  
- AI/LLM 辅助策略分析与执行前风险评估

### 项目介绍书（对外商务版）

BTT 是一个面向数字资产量化交易的开源智能交易平台，基于成熟的 Freqtrade 生态构建。  
它不仅支持策略开发、回测验证、自动执行和可视化运维，还具备面向 AI 时代的扩展能力，可用于构建“研究-验证-执行-复盘”一体化流程。

**我们能带来的价值：**

- **更快的策略落地速度**：从策略想法到回测验证再到运行部署，流程完整且工具齐全。  
- **更稳的上线路径**：支持先离线验证、再模拟运行、后实盘迭代，降低试错成本。  
- **更强的智能化潜力**：已预留 FreqAI 与智能体协作扩展点，便于后续接入外部模型与 AI 工作流。  
- **更低的长期维护成本**：开源透明、文档完善、接口标准化，支持团队持续演进。

**差异化优势：**

- 不只是“单策略脚本”，而是完整交易工程体系。  
- 不只是“自动下单”，而是强调风险控制与可观测性的可运营平台。  
- 不只是“当前可用”，而是为 AI/LLM 深度融合预留了可扩展基础能力。

### 项目介绍书（技术评审版）

BTT 采用“配置驱动 + 策略插件 + API 管理 + AI 扩展”架构，目标是在不破坏核心交易行为的前提下，持续提升策略研发效率与系统可维护性。

**技术结构特点：**

- **模块化边界清晰**：交易执行、策略逻辑、数据处理、API/WebUI、AI/FreqAI 能力相对解耦。  
- **策略生命周期完整**：支持数据准备、回测、优化、评估、运行监控与结果复盘。  
- **扩展机制稳定**：支持策略回调、模型解析器、REST 接口扩展与自定义流水线。  
- **工程化保障完善**：具备测试、文档与配置体系，降低迭代回归风险。

**AI 相关技术优势：**

- 提供标准化 FreqAI 模型接入接口，便于外部模型或混合推理逻辑落地。  
- 提供 AI Assistant 引导型 API 与可编辑 Roundtable Prompt 配置能力（含导入导出、启停开关、历史回滚）。  
- 通过渐进式验证路径（回测/模拟/实盘）保障 AI 增强能力的可控上线。

**评审关注点（本项目表现）：**

- **可扩展性**：支持新策略、新模型、新工作流按模块增量接入。  
- **可观测性**：可通过 WebUI / API / 日志进行状态追踪与问题定位。  
- **可维护性**：文档与测试覆盖关键能力，便于多人协作和长期维护。  
- **风险可控性**：强调非破坏性改造与安全回退机制，避免对核心交易行为造成突变。

## Disclaimer

This software is for educational purposes only. Do not risk money which
you are afraid to lose. USE THE SOFTWARE AT YOUR OWN RISK. THE AUTHORS
AND ALL AFFILIATES ASSUME NO RESPONSIBILITY FOR YOUR TRADING RESULTS.

Always start by running a trading bot in Dry-Run and do not engage money
before you understand how it works and what profit/loss you should
expect.

We strongly recommend you to have coding and Python knowledge. Do not
hesitate to read the source code and understand the mechanism of this bot.

## Supported Exchange marketplaces

Please read the [exchange-specific notes](https://www.freqtrade.io/en/stable/exchanges/) to learn about special configurations that maybe needed for each exchange.

### Supported Spot Exchanges

- [X] [Binance](https://www.binance.com/)
- [X] [BingX](https://bingx.com/invite/0EM9RX)
- [X] [Bitget](https://www.bitget.com/)
- [X] [Bybit EU](https://bybit.eu/)
- [X] [Bybit](https://bybit.com/)
- [X] [Gate EU](https://www.gate.com/en-eu)
- [X] [Gate](https://www.gate.com/ref/6266643)
- [X] [HTX](https://www.htx.com/)
- [X] [Hyperliquid](https://hyperliquid.xyz/) (A decentralized exchange, or DEX)
- [X] [Kraken](https://kraken.com/)
- [X] [MyOKX](https://okx.com/) (OKX EEA)
- [X] [OKX](https://okx.com/)
- [ ] [potentially many others](https://github.com/ccxt/ccxt/). _(We cannot guarantee they will work)_

### Supported Futures Exchanges

- [X] [Binance](https://www.binance.com/)
- [X] [Bitget](https://www.bitget.com/)
- [X] [Bybit](https://bybit.com/)
- [X] [Gate](https://www.gate.com/ref/6266643)
- [X] [Hyperliquid](https://hyperliquid.xyz/) (A decentralized exchange, or DEX)
- [X] [Kraken](https://www.kraken.com/features/futures)
- [X] [OKX](https://okx.com/)

Please make sure to read the [exchange specific notes](https://www.freqtrade.io/en/stable/exchanges/), as well as the [trading with leverage](https://www.freqtrade.io/en/stable/leverage/) documentation before diving in.

### Community tested

Exchanges confirmed working by the community:

- [X] [Bitvavo](https://bitvavo.com/)
- [X] [Kucoin](https://www.kucoin.com/)

## Documentation

We invite you to read the bot documentation to ensure you understand how the bot is working.

Please find the complete documentation on the [freqtrade website](https://www.freqtrade.io).

## Features

- [x] **Based on Python 3.11+**: For botting on any operating system - Windows, macOS and Linux.
- [x] **Persistence**: Persistence is achieved through sqlite.
- [x] **Dry-run**: Run the bot without paying money.
- [x] **Backtesting**: Run a simulation of your buy/sell strategy.
- [x] **Strategy Optimization by machine learning**: Use machine learning to optimize your buy/sell strategy parameters with real exchange data.
- [X] **Adaptive prediction modeling**: Build a smart strategy with FreqAI that self-trains to the market via adaptive machine learning methods. [Learn more](https://www.freqtrade.io/en/stable/freqai/)
- [x] **Whitelist crypto-currencies**: Select which crypto-currency you want to trade or use dynamic whitelists.
- [x] **Blacklist crypto-currencies**: Select which crypto-currency you want to avoid.
- [x] **Builtin WebUI**: Builtin web UI to manage your bot.
- [x] **Manageable via Telegram**: Manage the bot with Telegram.
- [x] **Display profit/loss in fiat**: Display your profit/loss in fiat currency.
- [x] **Performance status report**: Provide a performance status of your current trades.

## Quick start

Please refer to the [Docker Quickstart documentation](https://www.freqtrade.io/en/stable/docker_quickstart/) on how to get started quickly.

For further (native) installation methods, please refer to the [Installation documentation page](https://www.freqtrade.io/en/stable/installation/).

### One-click installers (Windows / macOS)

This repository includes one-click local installer scripts for backtesting and dry-run setup:

- **Windows**: `installers/windows/install-btt.bat` (or `install-btt.ps1`)
- **macOS**: `installers/macos/install-btt.command`

These scripts will:
1. Detect a supported Python version (3.11-3.14)
2. Create `.venv`
3. Install `requirements-dev.txt`
4. Install the project in editable mode
5. Install FreqUI (can be skipped)
6. Create a desktop-first local config at `user_data/config.local.desktop.json` (Telegram disabled by default)

After installation, they generate helper launchers (`run-backtest.ps1` / `run-backtest.sh`) for quick backtesting startup.

#### Desktop-first run (no Telegram)

Use the generated local config (desktop-focused, no mobile/Telegram dependency):

```bash
python -m freqtrade backtesting --config user_data/config.local.desktop.json --strategy SampleStrategy
```

#### Build install packages in CI

The workflow `.github/workflows/desktop-installers.yml` builds:
- **Windows EXE installer** artifact: `btt-windows-installer.exe`
- **macOS DMG installer** artifact: `btt-macos-installer.dmg`

Run this workflow from GitHub Actions (`workflow_dispatch`) and download artifacts from the run page.

#### Build macOS DMG locally (DRAFT branch check)

Use the following verified commands to build the local macOS installer image:

```bash
cd /home/runner/work/BTT/BTT
git fetch origin copilot/enhance-intelligence-layer-ai-improvements
git checkout origin/copilot/enhance-intelligence-layer-ai-improvements
chmod +x /home/runner/work/BTT/BTT/installers/macos/install-btt.command
bash /home/runner/work/BTT/BTT/installers/macos/build-dmg.sh
```

Output:

```text
/home/runner/work/BTT/BTT/dist/btt-macos-installer.dmg
```

## Basic Usage

### Bot commands

```
usage: freqtrade [-h] [-V]
                 {trade,create-userdir,new-config,show-config,new-strategy,download-data,convert-data,convert-trade-data,trades-to-ohlcv,list-data,backtesting,backtesting-show,backtesting-analysis,edge,hyperopt,hyperopt-list,hyperopt-show,list-exchanges,list-markets,list-pairs,list-strategies,list-hyperoptloss,list-freqaimodels,list-timeframes,show-trades,test-pairlist,convert-db,install-ui,plot-dataframe,plot-profit,webserver,strategy-updater,lookahead-analysis,recursive-analysis}
                 ...

Free, open source crypto trading bot

positional arguments:
  {trade,create-userdir,new-config,show-config,new-strategy,download-data,convert-data,convert-trade-data,trades-to-ohlcv,list-data,backtesting,backtesting-show,backtesting-analysis,edge,hyperopt,hyperopt-list,hyperopt-show,list-exchanges,list-markets,list-pairs,list-strategies,list-hyperoptloss,list-freqaimodels,list-timeframes,show-trades,test-pairlist,convert-db,install-ui,plot-dataframe,plot-profit,webserver,strategy-updater,lookahead-analysis,recursive-analysis}
    trade               Trade module.
    create-userdir      Create user-data directory.
    new-config          Create new config
    show-config         Show resolved config
    new-strategy        Create new strategy
    download-data       Download backtesting data.
    convert-data        Convert candle (OHLCV) data from one format to
                        another.
    convert-trade-data  Convert trade data from one format to another.
    trades-to-ohlcv     Convert trade data to OHLCV data.
    list-data           List downloaded data.
    backtesting         Backtesting module.
    backtesting-show    Show past Backtest results
    backtesting-analysis
                        Backtest Analysis module.
    hyperopt            Hyperopt module.
    hyperopt-list       List Hyperopt results
    hyperopt-show       Show details of Hyperopt results
    list-exchanges      Print available exchanges.
    list-markets        Print markets on exchange.
    list-pairs          Print pairs on exchange.
    list-strategies     Print available strategies.
    list-hyperoptloss   Print available hyperopt loss functions.
    list-freqaimodels   Print available freqAI models.
    list-timeframes     Print available timeframes for the exchange.
    show-trades         Show trades.
    test-pairlist       Test your pairlist configuration.
    convert-db          Migrate database to different system
    install-ui          Install FreqUI
    plot-dataframe      Plot candles with indicators.
    plot-profit         Generate plot showing profits.
    webserver           Webserver module.
    strategy-updater    updates outdated strategy files to the current version
    lookahead-analysis  Check for potential look ahead bias.
    recursive-analysis  Check for potential recursive formula issue.

options:
  -h, --help            show this help message and exit
  -V, --version         show program's version number and exit
```

### Telegram RPC commands

Telegram is not mandatory. However, this is a great way to control your bot. More details and the full command list on the [documentation](https://www.freqtrade.io/en/stable/telegram-usage/)

- `/start`: Starts the trader.
- `/stop`: Stops the trader.
- `/stopentry`: Stop entering new trades.
- `/status <trade_id>|[table]`: Lists all or specific open trades.
- `/profit [<n>]`: Lists cumulative profit from all finished trades, over the last n days.
- `/profit_long [<n>]`: Lists cumulative profit from all finished long trades, over the last n days.
- `/profit_short [<n>]`: Lists cumulative profit from all finished short trades, over the last n days.
- `/forceexit <trade_id>|all`: Instantly exits the given trade (Ignoring `minimum_roi`).
- `/fx <trade_id>|all`: Alias to `/forceexit`
- `/performance`: Show performance of each finished trade grouped by pair
- `/balance`: Show account balance per currency.
- `/daily <n>`: Shows profit or loss per day, over the last n days.
- `/help`: Show help message.
- `/version`: Show version.


## Development branches

The project is currently setup in two main branches:

- `develop` - This branch has often new features, but might also contain breaking changes. We try hard to keep this branch as stable as possible.
- `stable` - This branch contains the latest stable release. This branch is generally well tested.
- `feat/*` - These are feature branches, which are being worked on heavily. Please don't use these unless you want to test a specific feature.

## Support

### Help / Discord

For any questions not covered by the documentation or for further information about the bot, or to simply engage with like-minded individuals, we encourage you to join the Freqtrade [discord server](https://discord.gg/p7nuUNVfP7).

### [Bugs / Issues](https://github.com/freqtrade/freqtrade/issues?q=is%3Aissue)

If you discover a bug in the bot, please
[search the issue tracker](https://github.com/freqtrade/freqtrade/issues?q=is%3Aissue)
first. If it hasn't been reported, please
[create a new issue](https://github.com/freqtrade/freqtrade/issues/new/choose) and
ensure you follow the template guide so that the team can assist you as
quickly as possible.

For every [issue](https://github.com/freqtrade/freqtrade/issues/new/choose) created, kindly follow up and mark satisfaction or reminder to close issue when equilibrium ground is reached.

--Maintain github's [community policy](https://docs.github.com/en/site-policy/github-terms/github-community-code-of-conduct)--

### [Feature Requests](https://github.com/freqtrade/freqtrade/labels/enhancement)

Have you a great idea to improve the bot you want to share? Please,
first search if this feature was not [already discussed](https://github.com/freqtrade/freqtrade/labels/enhancement).
If it hasn't been requested, please
[create a new request](https://github.com/freqtrade/freqtrade/issues/new/choose)
and ensure you follow the template guide so that it does not get lost
in the bug reports.

### [Pull Requests](https://github.com/freqtrade/freqtrade/pulls)

Feel like the bot is missing a feature? We welcome your pull requests!

Please read the
[Contributing document](https://github.com/freqtrade/freqtrade/blob/develop/CONTRIBUTING.md)
to understand the requirements before sending your pull-requests.

Coding is not a necessity to contribute - maybe start with improving the documentation?
Issues labeled [good first issue](https://github.com/freqtrade/freqtrade/labels/good%20first%20issue) can be good first contributions, and will help get you familiar with the codebase.

**Note** before starting any major new feature work, *please open an issue describing what you are planning to do* or talk to us on [discord](https://discord.gg/p7nuUNVfP7) (please use the #dev channel for this). This will ensure that interested parties can give valuable feedback on the feature, and let others know that you are working on it.

**Important:** Always create your PR against the `develop` branch, not `stable`.

## Requirements

### Up-to-date clock

The clock must be accurate, synchronized to a NTP server very frequently to avoid problems with communication to the exchanges.

### Minimum hardware required

To run this bot we recommend you a cloud instance with a minimum of:

- Minimal (advised) system requirements: 2GB RAM, 1GB disk space, 2vCPU

### Software requirements

- [Python >= 3.11](http://docs.python-guide.org/en/latest/starting/installation/)
- [pip](https://pip.pypa.io/en/stable/installing/)
- [git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)
- [TA-Lib](https://ta-lib.github.io/ta-lib-python/)
- [virtualenv](https://virtualenv.pypa.io/en/stable/installation.html) (Recommended)
- [Docker](https://www.docker.com/products/docker) (Recommended)
