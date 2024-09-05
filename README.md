# Trading Bot

Este é um bot de negociação para Bitcoin usando a API da Binance. O bot realiza operações de compra e venda com base em dados históricos e parâmetros definidos em um arquivo de configuração. Ele também oferece opções de simulação e grava informações sobre as ordens em um banco de dados SQLite.

## Recursos

- Compra e venda automática de Bitcoin com base em análise técnica.
- Suporte para níveis de Fibonacci e cálculo de médias móveis.
- Registro de ordens em um banco de dados SQLite.
- Modo de simulação para testar o bot sem realizar transações reais.
- Logs detalhados para acompanhamento e depuração.

## Pré-requisitos

- Python 3.7 ou superior
- Biblioteca `binance` para interação com a API da Binance
- Bibliotecas adicionais: `keyboard`, `pandas`, `numpy`, `matplotlib`, `sqlite3`, `json`, `logging`
- Conta na Binance e chaves de API

## Instalação

## 1. Clone o repositório:
```bash
git clone https://github.com/enricomalta/TradingBot.git
cd TradingBot
```

## 2. Instale as dependências:
```bash
pip install binance pandas numpy matplotlib
```

## 3.Coloque sua API_KEY e API_SECRET da Binance no arquivo config.json na raiz do projeto:
Execute o bot:
```bash
python trading_bot.py
```

## 4. Estrutura do json e seu conceitos:
* API_KEY: Sua API da Binance
* API_SECRET: Sua API Secrete da Binance
* SYMBOL: Nome da moeda negociada
* MOEDA: Moeda que irá utilizar Exemplo: BRL
* BUY_MIN: Valor min para efetuar uma ordem de compra
* BUY_PRICE: Valor da ordem de compra
* ORDEM_MARGIN: Valor da venda da quantidade do ativo com base na % com referencia no preço da compra Exemplo: Comprou a 100k chegou a 116K com uma ordem margin de 16 ele ira vender automatico
* FIBONACCI_TOLERANCE: Margem de erro do Fibonnaci
* PERCENTAGE_TO_USE: Porcentagem da sua carteira que deve ser usada quando o BALANCE_SAFE é menor que o seu saldo da carteira
* BALANCE_SAFE: Valor que você quer assegurar
* TIME_CHECK: Tempo que o bot ira fazer as operações
* SIMULATION_MODE: Ativa modo simulação
* SIMULATION_BALANCE: Simular um valor na carteira
* SIMULATION_PRICE: Simula um valor do ativo


## Estrutura do Código
Funções Principais
* load_config(filepath: str) -> Dict[str, Any]: Carrega e valida o arquivo de configuração JSON.
* initialize_client(api_key: str, api_secret: str): Inicializa o cliente da Binance.
* initialize_database(): Inicializa o banco de dados SQLite e cria a tabela de ordens.
* insert_order(date_buy: str, quantity: float, buy_price: float, target_price: float) -> int: Insere uma nova ordem de compra no banco de dados.
* update_order_status(order_ids: list, status: str, sell_price: float): Atualiza o status e o preço de venda das ordens no banco de dados.
* get_fibonacci_levels(current_price: float): Calcula os níveis de Fibonacci com base no preço atual.
* get_btc_brl_price() -> float: Obtém o preço atual do BTC/BRL da Binance.

## 5. Futuras implantações
* get_trading_fees() -> Tuple[float, float]: Obtém as taxas de negociação da Binance.
* get_historical_data(client, symbol, interval='1d', lookback='30 days'): Obtém dados históricos de preços.
* strategy(df): Implementa a estratégia de negociação com base em médias móveis.
* plot_strategy(df): Plota os resultados da estratégia de negociação.
* calculate_support_resistance(prices: list) -> Tuple[float, float]: Calcula suporte e resistência.
* calculate_rsi(prices: list, period: int = 14) -> float: Calcula o Índice de Força Relativa (RSI).
* detect_hammer_candle(open_price, close_price, low_price, high_price): Detecta o padrão de vela Martelo.

## 6. Execução
* A função principal trade() realiza a negociação com base nas configurações e parâmetros definidos, as ordens são salvas em um banco de dados que pode executar uma ordem de venda caso atinja o criterio da ORDEM_MARGIN com base no preço da compra. Ela também lida com o modo simulação caso queira testar uma estrategia sem colocar em risco seu patrimônio

## 7. Logs e Banco de Dados
Os logs são armazenados em logs/trading_bot.log.
As ordens são registradas em um banco de dados SQLite chamado orders.db.

## 8. Contribuições
Contribuições são bem-vindas! Por favor, faça um fork do repositório e envie um pull request com suas melhorias.

## 9. Licença
- Este projeto está licenciado sob a Licença MIT - veja o arquivo LICENSE para mais detalhes.
