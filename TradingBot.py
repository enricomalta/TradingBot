from binance.client import Client  # type: ignore
from binance.exceptions import BinanceAPIException  # type: ignore
import keyboard
import time
import json
import logging
import os
import sys
import sqlite3
from typing import Dict, Any, Tuple
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from multiprocessing import Process, Queue, Event

###################### HANDLERS ######################

## CARREGA JSON
def load_config(filepath: str) -> Dict[str, Any]:
    try:
        with open(filepath, "r") as file:
            config = json.load(file)
    except FileNotFoundError:
        logger.error(f"Arquivo de configuração '{filepath}' não encontrado.")
        raise
    except json.JSONDecodeError:
        logger.error(f"Erro ao decodificar o arquivo de configuração '{filepath}'.")
        raise
    return config
## CONFIGURAÇÕES DE LOG
log_folder = 'logs'
if not os.path.exists(log_folder):
    os.makedirs(log_folder)
logger = logging.getLogger()
logger.setLevel(logging.INFO)
## HANDLER PARA O ARQUIVO DE LOG
file_handler = logging.FileHandler(os.path.join(log_folder, 'trading_bot.log'), encoding='utf-8')
file_handler.setLevel(logging.INFO)
## HANDLER PARA O TERMINAL
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
## FORMATADOR PARA OS HANDLERS
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)
## ADICIONA OS HANDLERS AO LOGGER
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

## CONFIGURAÇÕES
config = load_config("config.json")
API_KEY = config.get("API_KEY", "")
API_SECRET = config.get("API_SECRET", "")
INTERVAL = config.get("INTERVAL", "")
LOOKBACK = config.get("LOOKBACK", "")
SYMBOL = config.get("SYMBOL")
BUY_MIN = float(config["BUY_MIN"])
BUY_PRICE = float(config["BUY_PRICE"])
ORDER_MARGIN = float(config["ORDER_MARGIN"]) / 100
FIBONACCI_LEVELS = [0.236, 0.382, 0.5, 0.618, 0.764]  # Níveis de Fibonacci
FIBONACCI_TOLERANCE = float(config["FIBONACCI_TOLERANCE"]) / 100
PERCENTAGE_TO_USE = float(config["PERCENTAGE_TO_USE"]) / 100
BALANCE_SAFE = float(config["BALANCE_SAFE"])
TIME_CHECK = int(config["TIME_CHECK"])
SIMULATION_MODE = config.get("SIMULATION_MODE", False)  # Modo de simulação
SIMULATION_BALANCE = float(config["SIMULATION_BALANCE"])
SIMULATION_PRICE = float(config["SIMULATION_PRICE"])
TRADE_CRITERIA = config.get("TRADE_CRITERIA", "fibonacci")  # Critério de trade: "fibonacci" ou "support_resistance"

## CONFIG JSON FILE
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(__file__)
config_path = os.path.join(base_path, 'config.json')
## VALIDAÇÃO DE DADOS
if not API_KEY or not API_SECRET:
    logger.error("Chaves de API não fornecidas.")
    raise ValueError("Chaves de API não fornecidas.")
if not SYMBOL or PERCENTAGE_TO_USE <= 0:
    logger.error("Configuração inválida detectada.")
    raise ValueError("Configuração inválida detectada.")








###################### CONECCTIONS ######################


## INICIALIZA O CLIENTE BINANCE
def initialize_client(api_key, api_secret):
    return Client(api_key, api_secret)
## INICIALIZA O BANCO DE DADOS SQLITE
def initialize_database():
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_buy TEXT,
            quantity REAL,
            buy_price REAL,
            target_price REAL,
            sell_price REAL,
            value_purchased REAL,
            value_end REAL,
            profit REAL,
            date_sell TEXT,
            status TEXT
        )
    ''')
    conn.commit()
    return conn, c
## INSERE ORDEM DE COMPRA
def insert_order(date_buy: str, quantity: float, buy_price: float, target_price: float) -> int:
    try:
        conn = sqlite3.connect('orders.db')
        c = conn.cursor()
        
        # Calcula o valor de compra no momento da compra
        value_purchased = quantity * buy_price
        
        # Insere a ordem no banco de dados
        c.execute('''
            INSERT INTO orders (date_buy, quantity, buy_price, target_price, sell_price, value_purchased, value_end, profit, date_sell, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (date_buy, quantity, buy_price, target_price, None, value_purchased, None, None, None,'open'))
        
        conn.commit()
        order_id = c.lastrowid  # Obtém o ID da última ordem inserida
        conn.close()
        
        logger.info(f"Ordem de compra: ID {order_id}, Data: {date_buy}, Quantidade: {quantity}, Valor de Compra: {value_purchased}, Preço de Compra: {buy_price}, Preço alvo: {target_price}")
        return order_id
    except sqlite3.Error as e:
        logger.error(f"Erro ao inserir ordem no banco de dados: {e}")
        raise
## ATUALIZA ORDEM DE VENDA
def update_order_status(order_ids: list, status: str, sell_price: float):
    try:
        conn = sqlite3.connect('orders.db')
        c = conn.cursor()

        total_profit = 0.0  # Inicializa o lucro total
        updated_order_ids = []  # Para armazenar IDs das ordens atualizadas

        for order_id in order_ids:
            # Recupera o preço de compra, a quantidade e o valor de compra para calcular o lucro
            c.execute('SELECT buy_price, quantity, value_purchased FROM orders WHERE id = ?', (order_id,))
            result = c.fetchone()

            if result:
                buy_price, quantity, value_purchased = result

                # Verifica se buy_price e quantity são números válidos
                try:
                    buy_price = float(buy_price) if buy_price is not None else 0.0
                    quantity = float(quantity) if quantity is not None else 0.0
                    value_purchased = float(value_purchased) if value_purchased is not None else 0.0
                except ValueError as ve:
                    logger.error(f"Erro ao converter valores numéricos para ID {order_id}: {ve}")
                    continue

                # Calcula o valor final da venda e o lucro
                try:
                    value_end = sell_price * quantity
                    profit = value_end - value_purchased
                except TypeError as te:
                    logger.error(f"Erro ao calcular lucro para ID {order_id}: {te}")
                    continue

                total_profit += profit  # Acumula o lucro total

                # Atualiza a ordem no banco de dados
                c.execute('''
                    UPDATE orders
                    SET status = ?, sell_price = ?, value_end = ?, profit = ?, date_sell = ?
                    WHERE id = ?
                ''', (status, sell_price, value_end, profit, time.strftime('%Y-%m-%d %H:%M:%S'), order_id))
                
                updated_order_ids.append(order_id)
                
                # Log para cada ordem atualizada
                logger.info(f"Ordem atualizada: ID {order_id}, Status: {status}, Preço de venda: {sell_price}, Valor final: {value_end:.2f}, Lucro: {profit:.2f}")

        conn.commit()
        conn.close()

        # Log do lucro total após a atualização de todas as ordens
        logger.info(f"Lucro total das ordens vendidas: R${total_profit:.2f}")
        logger.info(f"Ordens atualizadas: IDs {updated_order_ids}, Status: {status}, Preço de venda: {sell_price}")

    except sqlite3.Error as e:
        logger.error(f"Erro ao atualizar ordens no banco de dados: {e}")
        raise
    except Exception as ex:
        logger.error(f"Erro inesperado: {ex}")
        raise
## OBTÉM O PREÇO MAIS RECENTE E CALCULA OS NÍVEIS DE FIBONACCI
def get_fibonacci_levels(current_price: float):
    levels = [current_price - (current_price * level) for level in FIBONACCI_LEVELS]
    return levels
## OBTÉM O PREÇO ATUAL DO BTC/BRL
def get_btc_brl_price() -> float:
    try:
        ticker = client.get_symbol_ticker(symbol=SYMBOL)
        return float(ticker['price'])
    except BinanceAPIException as e:
        logger.error(f"Erro ao obter preço do BTC/BRL: {e}")
        return 0.0
client = initialize_client(API_KEY, API_SECRET)
conn, c = initialize_database()


###################### IMPLATANÇÕES ######################


## OBTÉM AS TAXAS DE NEGOCIAÇÃO
def get_trading_fees() -> Tuple[float, float]:
    try:
        account_info = client.get_account()
        # Corrigir as taxas para valores decimais corretos
        maker_fee = float(account_info['makerCommission']) / 10000  # Dividir por 10000 para obter 0.001 (0,1%)
        taker_fee = float(account_info['takerCommission']) / 10000  # Dividir por 10000 para obter 0.001 (0,1%)
        logger.info(f"Taxas obtidas - Maker: {maker_fee * 100}%, Taker: {taker_fee * 100}%")
        return maker_fee, taker_fee
    except BinanceAPIException as e:
        logger.error(f"Erro ao obter taxas de negociação: {e}")
        return 0.0, 0.0
## HISTORICO
def get_historical_data(client, SYMBOL, INTERVAL, LOOKBACK):
    try:
        df = pd.DataFrame(client.get_historical_klines(SYMBOL, INTERVAL, LOOKBACK))
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 
                      'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 
                      'taker_buy_quote_asset_volume', 'ignore']
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df = df.astype(float)
        logger.info("Dados históricos obtidos com sucesso.")
        return df
    except BinanceAPIException as e:
        logger.error(f"Erro ao obter dados históricos: {e}")
        return pd.DataFrame()  # Retorna um DataFrame vazio em caso de erro
## CALCULO DO PROFIT
def calcular_lucro_liquido(preco_compra, preco_venda, quantidade, maker_fee, taker_fee):
    # Calcula as taxas
    taxa_compra = preco_compra * quantidade * maker_fee
    taxa_venda = preco_venda * quantidade * taker_fee
    taxas_totais = taxa_compra + taxa_venda

    # Calcula o lucro líquido
    lucro_liquido = (preco_venda * quantidade) - (preco_compra * quantidade) - taxas_totais
    return lucro_liquido
## VERIFICA LUCRO
def verificar_lucro(preco_compra, preco_venda, quantidade):
    maker_fee, taker_fee = get_trading_fees(client)  # Obtém as taxas da Binance
    lucro_liquido = calcular_lucro_liquido(preco_compra, preco_venda, quantidade, maker_fee, taker_fee)

    if lucro_liquido > 0:
        logger.info(f"Lucro líquido esperado: R${lucro_liquido:.2f}. Venda é lucrativa.")
        return True
    else:
        logger.info(f"Lucro líquido esperado: R${lucro_liquido:.2f}. Venda não é lucrativa.")
        return False
## Função para exibir e atualizar o gráfico em um processo separado
def plot_strategy_process(queue, stop_event):
    plt.ion()  # Ativa o modo interativo
    fig, ax = plt.subplots(figsize=(12, 8))
    last_df = None  # Armazena o último DataFrame recebido

    while not stop_event.is_set():  # Verifica se o evento de parada foi acionado
        try:
            if not queue.empty():
                df = queue.get_nowait()  # Obtém o DataFrame atualizado sem bloquear
                if df is None:  # Sinal para encerrar o processo
                    break
                if not df.empty and 'close' in df.columns and 'SMA_50' in df.columns and 'SMA_200' in df.columns:
                    last_df = df  # Atualiza o último DataFrame válido recebido

            if last_df is not None:  # Se houver dados válidos, atualiza o gráfico
                ax.clear()  # Limpa o gráfico para atualizar
                ax.plot(last_df.index, last_df['close'], label='Close Price', alpha=0.5)
                ax.plot(last_df.index, last_df['SMA_50'], label='SMA 50', alpha=0.75)
                ax.plot(last_df.index, last_df['SMA_200'], label='SMA 200', alpha=0.75)

                # Adiciona os sinais de compra e venda
                buy_signals = last_df[last_df['position'] == 1]
                sell_signals = last_df[last_df['position'] == -1]

                # Plota os sinais de compra
                ax.plot(buy_signals.index, buy_signals['close'], '^', markersize=10, color='g', lw=0, label='Buy Signal')
                for idx, row in buy_signals.iterrows():
                    ax.text(idx, row['close'], f"{row['close']:.2f}", color='green', fontsize=8)

                # Plota os sinais de venda
                ax.plot(sell_signals.index, sell_signals['close'], 'v', markersize=10, color='r', lw=0, label='Sell Signal')
                for idx, row in sell_signals.iterrows():
                    ax.text(idx, row['close'], f"{row['close']:.2f}", color='red', fontsize=8)

                ax.set_title('Trading Strategy')
                ax.legend()
                plt.draw()
                plt.pause(0.5)  # Atualiza o gráfico com menor frequência
        except Exception as e:
            logger.error(f"Erro no processo do gráfico: {e}")
            break

    plt.close(fig)  # Fecha o gráfico ao encerrar o processo

## ESTRATEGIA
def strategy(df):
    if df.empty:
        logger.error("O DataFrame de dados históricos está vazio.")
        return df

    # Calcular as médias móveis
    df['SMA_50'] = df['close'].rolling(window=50).mean()
    df['SMA_200'] = df['close'].rolling(window=200).mean()
    
    # Inicializar a coluna 'signal' com 0
    df['signal'] = 0
    
    # Definir sinais usando .iloc para evitar problemas com o índice
    if len(df) > 200:  # Garante que há dados suficientes
        df.iloc[200:, df.columns.get_loc('signal')] = np.where(
            df['SMA_50'].iloc[200:] > df['SMA_200'].iloc[200:], 1, 0
        )
    
    # Calcular a coluna 'position' para detectar mudanças de sinal
    df['position'] = df['signal'].diff()
    
    return df

# Execução das funções

###################### METRICAS TRADING ######################


## CALCULA SUPORTE E RESISTÊNCIA
def calculate_support_resistance(prices: list) -> Tuple[float, float]:
    """Calcula o suporte e resistência com base nos preços."""
    if not prices:
        logger.error("Nenhum preço disponível para calcular suporte e resistência.")
        return 0.0, 0.0

    suporte = min(prices)  # Suporte é o menor preço do período
    resistencia = max(prices)  # Resistência é o maior preço do período

    logger.info(f"Suporte calculado: R${suporte:.2f}, Resistência calculada: R${resistencia:.2f}")
    return suporte, resistencia
## CÁLCULO DO RSI
def calculate_rsi(prices: list, period: int = 14) -> float:
    if len(prices) < period:
        logger.error("Não há preços suficientes para calcular o RSI.")
        return 0.0

    # Cálculo das variações de preço
    gains = [prices[i] - prices[i-1] for i in range(1, len(prices)) if prices[i] > prices[i-1]]
    losses = [prices[i-1] - prices[i] for i in range(1, len(prices)) if prices[i] < prices[i-1]]

    average_gain = sum(gains) / period
    average_loss = sum(losses) / period

    if average_loss == 0:
        return 100

    rs = average_gain / average_loss
    rsi = 100 - (100 / (1 + rs))
    logger.info(f"RSI calculado: {rsi:.2f}")
    return rsi
## DETECTA PADRÃO DE VELA
def detect_hammer_candle(open_price, close_price, low_price, high_price):
    """Detecta padrão de martelo nas velas."""
    if close_price > open_price and (high_price - close_price) < (close_price - low_price) * 0.2:
        logger.info("Padrão de Martelo identificado - Possível reversão de tendência.")
        return True
    return False



###################### LOOP ######################


## FUNÇÃO PRINCIPAL DE NEGOCIAÇÃO
def trade():
    try: 
        # Obter o preço atual e saldo
        if SIMULATION_MODE:
            price = SIMULATION_PRICE
            current_price = price
            balance = SIMULATION_BALANCE
            logger.info(f"Preço simulado do {SYMBOL}: R${current_price:.2f}")
            logger.info(f"Saldo simulado disponível: R${balance:.2f}")
        else:
            current_price = get_btc_brl_price()
            logger.info(f"Preço atual do {SYMBOL}: R${current_price:.2f}")
            asset_balance = client.get_asset_balance(asset='BRL')
            balance = float(asset_balance['free'])
            logger.info(f"Saldo disponível: R${balance:.2f}")

        # Obter dados históricos para calcular suporte e resistência
        df = get_historical_data(client, SYMBOL, INTERVAL, LOOKBACK)
        if df.empty:
            logger.error("Não foi possível obter dados históricos para calcular suporte e resistência.")
            return

        # Calcular suporte e resistência
        suporte, resistencia = calculate_support_resistance(df['close'].tolist())
        logger.info(f"Suporte: R${suporte:.2f}, Resistência: R${resistencia:.2f}")

        # Calcular níveis de Fibonacci
        fibonacci_levels = get_fibonacci_levels(current_price)
        logger.info(f"Níveis de Fibonacci: {fibonacci_levels}")

        # Definir o valor a ser usado na compra
        if balance < BALANCE_SAFE:
            amount_to_use = balance
        else:
            amount_to_use = balance * PERCENTAGE_TO_USE

        # Verificar se o valor a ser usado é suficiente para a compra mínima
        if amount_to_use < BUY_MIN:
            logger.info(f"Ignorando a compra R${amount_to_use:.2f} abaixo do mínimo R${BUY_MIN:.2f}.")
            logger.info("-----------------------------------------------------------------------------------")
        else:
            # Calcular a quantidade a ser comprada e o preço alvo
            quantity_to_buy = amount_to_use / current_price
            buy_price = current_price
            target_price = buy_price * (1 + ORDER_MARGIN)

            logger.info(f"Valor da compra: R${amount_to_use:.2f}")
            logger.info(f"Quantidade de BTC a ser comprada: {quantity_to_buy}")
            logger.info(f"Preço alvo calculado: {target_price:.2f}")

            # Escolher o critério de trade
            if TRADE_CRITERIA == "fibonacci":
                logger.info("Usando critério de Fibonacci para trade.")
                if current_price <= BUY_PRICE and current_price >= fibonacci_levels[0]:
                    logger.info(f"Preço atual ({current_price:.2f}) atende ao critério de Fibonacci ({fibonacci_levels[0]}).")
                    logger.info("-----------------------------------------------------------------------------------")
                    if SIMULATION_MODE:
                        logger.info("Modo de simulação ativado. Comprando Bitcoin...")
                        insert_order(time.strftime('%Y-%m-%d %H:%M:%S'), quantity_to_buy, buy_price, target_price)
                        logger.info(f"[SIMULATED BUY] Compra simulada registrada: Quantidade: {quantity_to_buy} BTC a R${buy_price}")
                        logger.info("-----------------------------------------------------------------------------------")
                    else:
                        logger.info("Comprando Bitcoin...")
                        order = client.order_market_buy(symbol=SYMBOL, quantity=quantity_to_buy)
                        insert_order(time.strftime('%Y-%m-%d %H:%M:%S'), quantity_to_buy, buy_price, target_price)
                        logger.info(f"[BUY] Compra realizada: {order}")
                        logger.info("-----------------------------------------------------------------------------------")
                else:
                    logger.info(f"Preço atual ({current_price:.2f}) não atende aos critérios de Fibonacci.")
                    logger.info("-----------------------------------------------------------------------------------")
            elif TRADE_CRITERIA == "support_resistance":
                logger.info("Usando critério de suporte/resistência para trade.")
                if current_price <= suporte * (1 + FIBONACCI_TOLERANCE):
                    logger.info(f"Preço atual ({current_price}) está próximo do suporte ({suporte}).")
                    logger.info("-----------------------------------------------------------------------------------")
                    if SIMULATION_MODE:
                        logger.info("Modo de simulação ativado. Comprando Bitcoin...")
                        insert_order(time.strftime('%Y-%m-%d %H:%M:%S'), quantity_to_buy, buy_price, resistencia)
                        logger.info(f"[SIMULATED BUY] Compra simulada registrada: Quantidade: {quantity_to_buy} BTC a R${buy_price:.2f}")
                        logger.info("-----------------------------------------------------------------------------------")
                    else:
                        logger.info("Comprando Bitcoin...")
                        order = client.order_market_buy(symbol=SYMBOL, quantity=quantity_to_buy)
                        insert_order(time.strftime('%Y-%m-%d %H:%M:%S'), quantity_to_buy, buy_price, resistencia)
                        logger.info(f"[BUY] Compra realizada: {order}")
                        logger.info("-----------------------------------------------------------------------------------")
                else:
                    logger.info(f"Preço atual ({current_price}) não está próximo do suporte ({suporte}).")
                    logger.info("-----------------------------------------------------------------------------------")
            else:
                logger.error(f"Critério de trade inválido: {TRADE_CRITERIA}")
                return
        
        # Consolidar ordens para venda
        conn = sqlite3.connect('orders.db')
        c = conn.cursor()
        c.execute('SELECT * FROM orders WHERE status = "open"')
        open_orders = c.fetchall()

        if open_orders:
            total_quantity = sum(order[2] for order in open_orders)  # Quantidade total de ordens abertas
            sell_orders = [order for order in open_orders if current_price >= order[4]]  # Filtra ordens para venda

            if sell_orders:
                order_ids = []
                for order in sell_orders:
                    if verificar_lucro(preco_compra=order[3], preco_venda=current_price, quantidade=order[2]):
                        logger.info(f"Venda será realizada para a ordem ID {order[0]}, pois é lucrativa.")
                        if SIMULATION_MODE:
                            logger.info(f"[SIMULATED SELL] Ordem ID {order[0]}: Vendendo {order[2]} BTC a R${current_price:.2f}.")
                        else:
                            client.order_market_sell(symbol=SYMBOL, quantity=order[2])
                        order_ids.append(order[0])
                    else:
                        logger.info(f"Venda não será realizada para a ordem ID {order[0]}, pois não é lucrativa.")

                if order_ids:
                    update_order_status(order_ids, 'closed', current_price)
                    logger.info("Ordens lucrativas foram fechadas.")
                    logger.info("-----------------------------------------------------------------------------------")

    except BinanceAPIException as e:
        logger.error(f"Erro na API Binance: {e}")
    except Exception as e:
        logger.error(f"Erro inesperado: {e}")
## VERIFICA SE A TECLA ESC FOI PRESSIONADA E RETORNA O ESTADO
def check_pause_condition():
    return keyboard.is_pressed('esc')
## FUNÇÃO PRINCIPAL
def main():
    # Inicializa a fila para comunicação entre processos
    queue = Queue()
    stop_event = Event()

    # Inicia o processo do gráfico
    plot_process = Process(target=plot_strategy_process, args=(queue, stop_event))
    plot_process.start()

    paused = False
    last_run_time = time.time()  # Guarda o tempo da última execução
    first_run = True  # Flag para verificar a primeira execução
    try:    
        while True:
            current_time = time.time()

            # Verifica se a tecla ESC foi pressionada
            if keyboard.is_pressed('esc'):
                paused = not paused
                if paused:
                    logger.info("Programa pausado. Pressione ESC novamente para retomar.")
                else:
                    logger.info("Programa retomado.")
                time.sleep(1)  # Adiciona um atraso para evitar múltiplas detecções

            if not paused:
                if first_run or current_time - last_run_time >= TIME_CHECK:
                    try:
                        # Executa o bot
                        trade()

                        # Atualiza o DataFrame e envia para o processo do gráfico
                        df = get_historical_data(client, SYMBOL, INTERVAL, LOOKBACK)
                        df = strategy(df)
                        if not df.empty:
                            if queue.qsize() < 5:  # Limita o tamanho da fila para evitar sobrecarga
                                queue.put(df)  # Envia o DataFrame atualizado para o gráfico
                            else:
                                logger.warning("Fila cheia. Ignorando envio de dados para o gráfico.")
                        else:
                            logger.error("DataFrame vazio, não enviado para o gráfico.")
                    except Exception as e:
                        logger.error(f"Erro na função trade: {e}")
                    last_run_time = current_time
                    first_run = False
                else:
                    time.sleep(1)
            else:
                time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Encerrando o programa...")
    finally:
        stop_event.set()  # Sinaliza para o processo do gráfico encerrar
        queue.put(None)  # Envia sinal para encerrar o processo do gráfico
        plot_process.join()  # Aguarda o término do processo do gráfico

client = initialize_client(API_KEY, API_SECRET)
conn, c = initialize_database()

## VALIDAÇÃO DE MARGEM DE ORDEM
maker_fee, taker_fee = get_trading_fees()
total_fees = maker_fee + taker_fee


if ORDER_MARGIN <= total_fees:
    logger.warning(f"ORDER_MARGIN ({ORDER_MARGIN * 100:.2f}%) é menor ou igual às taxas totais ({total_fees * 100:.4f}%). Ajustando para garantir lucro.")
    ORDER_MARGIN = total_fees + 0.01  # Adiciona 1% acima das taxas para garantir lucro
    logger.info(f"ORDER_MARGIN ajustado para: {ORDER_MARGIN * 100:.2f}%")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Erro inesperado: {e}")
        input("Pressione qualquer tecla para sair...")  # Mantém a janela aberta para ver o erro
