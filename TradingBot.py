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
import threading

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
        maker_fee = float(account_info['makerCommission']) / 100
        taker_fee = float(account_info['takerCommission']) / 100
        logger.info(f"Taxas obtidas - Maker: {maker_fee}, Taker: {taker_fee}")
        return maker_fee, taker_fee
    except BinanceAPIException as e:
        logger.error(f"Erro ao obter taxas de negociação: {e}")
        return 0.0, 0.0
## HISTORICO 30D
def get_historical_data(client, symbol, interval='1d', lookback='30 days'):
    try:
        df = pd.DataFrame(client.get_historical_klines(symbol, interval, lookback))
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
## PLOTAR RESULTADOS
def plot_strategy(df):
    if df.empty:
        logger.error("O DataFrame está vazio, não é possível plotar a estratégia.")
        return

    plt.figure(figsize=(12,8))
    plt.plot(df.index, df['close'], label='Close Price', alpha=0.5)
    plt.plot(df.index, df['SMA_50'], label='SMA 50', alpha=0.75)
    plt.plot(df.index, df['SMA_200'], label='SMA 200', alpha=0.75)
    
    plt.plot(df[df['position'] == 1].index, df['SMA_50'][df['position'] == 1], '^', markersize=10, color='g', lw=0, label='Buy Signal')
    plt.plot(df[df['position'] == -1].index, df['SMA_50'][df['position'] == -1], 'v', markersize=10, color='r', lw=0, label='Sell Signal')
    
    plt.title('Trading Strategy')
    plt.legend()
    plt.show()

# Execução das funções
# df = get_historical_data(client, SYMBOL, INTERVAL, LOOKBACK)
# df = strategy(df)
# plot_strategy(df)
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
            logger.info(f"Preço simulado do {SYMBOL}: R${current_price}")
            logger.info(f"Saldo simulado disponível: R${balance}")
        else:
            current_price = get_btc_brl_price()
            logger.info(f"Preço atual do {SYMBOL}: R${current_price}")
            asset_balance = client.get_asset_balance(asset='BRL')
            balance = float(asset_balance['free'])
            logger.info(f"Saldo disponível: R${balance}")

        # Definir o valor a ser usado na compra
        if balance < BALANCE_SAFE:
            amount_to_use = balance
        else:
            amount_to_use = balance * PERCENTAGE_TO_USE

        # Verificar se o valor a ser usado é suficiente para a compra mínima
        if amount_to_use < BUY_MIN:
            logger.info(f"Ignorando a compra R${amount_to_use} abaixo do mínimo R${BUY_MIN}.")
            logger.info("-----------------------------------------------------------------------------------")
        else:
            # Calcular a quantidade a ser comprada, o preço alvo e os níveis de Fibonacci
            quantity_to_buy = amount_to_use / current_price
            buy_price = current_price
            target_price = buy_price * (1 + ORDER_MARGIN)
            fibonacci_levels = get_fibonacci_levels(current_price)

            logger.info(f"Valor da compra: R${amount_to_use}")
            logger.info(f"Quantidade de BTC a ser comprada: {quantity_to_buy}")
            logger.info(f"Preço alvo calculado: {target_price}")
            logger.info(f"Níveis de Fibonacci: {fibonacci_levels}")
            logger.info(f"Comparando preço atual ({current_price}) com nível de Fibonacci mais baixo ({fibonacci_levels[0]})")
            logger.info(f"Comparando preço atual ({current_price}) com preço da ordem de compra ({BUY_PRICE})")
            
            # Verifica se o preço atual atende ao critério de Fibonacci e ao preço da ordem de compra
            if current_price <= BUY_PRICE and current_price >= fibonacci_levels[0]:
                logger.info(f"Preço atual ({current_price}) atende ao critério de Fibonacci ({fibonacci_levels[0]}) e está abaixo da ordem de compra ({BUY_PRICE})")
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
                logger.info(f"Preço atual ({current_price}) não atende aos critérios de Fibonacci ({fibonacci_levels[0]}) e/ou está acima da ordem de compra ({BUY_PRICE})")
                logger.info("-----------------------------------------------------------------------------------")
        
        # Consolidar ordens para venda
        conn = sqlite3.connect('orders.db')
        c = conn.cursor()
        c.execute('SELECT * FROM orders WHERE status = "open"')
        open_orders = c.fetchall()

        if open_orders:
            total_quantity = sum(order[2] for order in open_orders)  # Quantidade total de ordens abertas
            sell_orders = [order for order in open_orders if current_price >= order[4]]  # Filtra ordens para venda

            if sell_orders:
                order_ids = [order[0] for order in sell_orders]
                if SIMULATION_MODE:
                    logger.info("Modo de simulação ativado. Vendendo Bitcoin...")
                    for order in sell_orders:
                        order_id = order[0]
                        #date_buy = order[1]
                        quantity = order[2]
                        buy_price = order[3]
                        target_price = order[4]
                        value_purchased = order[6]
                        value_end = current_price * quantity
                        profit = value_end - value_purchased
                        logger.info(
                            f"[SIMULATED SELL] Ordem ID {order_id}: Vendendo {quantity} BTC a {current_price} BRL. "
                            f"Valor comprado: {value_purchased:.2f} BRL, Valor final: {value_end:.2f} BRL, "
                            f"Lucro: {profit:.2f} BRL."
                        )
                    update_order_status(order_ids, 'closed', current_price)
                    logger.info("Todas as ordens de venda simuladas foram fechadas.")
                    logger.info("-----------------------------------------------------------------------------------")
                else:
                    logger.info("Vendendo Bitcoin...")
                    order = client.order_market_sell(symbol=SYMBOL, quantity=total_quantity)
                    update_order_status(order_ids, 'closed', current_price)
                    logger.info("[SELL] Venda realizada: %s", order)
                    for order_id in order_ids:
                        c.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
                        updated_order = c.fetchone()
                        if updated_order:
                            id = updated_order[0]
                            #date_buy = updated_order[1]
                            quantity = updated_order[2]
                            buy_price = updated_order[3]
                            target_price = updated_order[4]
                            sell_price = updated_order[5]
                            value_purchased = updated_order[6]
                            value_end = updated_order[7]
                            profit = updated_order[8]
                            date_sell = updated_order[9]
                            status = updated_order[10]
                            logger.info(
                                f"[SELL] Ordem ID {id}: Vendido {quantity} BTC a {sell_price} BRL. "
                                f"Valor comprado: {value_purchased:.2f} BRL, Valor final: {value_end:.2f} BRL, "
                                f"Lucro: {profit:.2f} BRL. Data de venda: {date_sell}, Status: {status}"
                            )
                    logger.info("Todas as ordens de venda foram fechadas.")
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
    paused = False
    last_run_time = time.time()  # Guarda o tempo da última execução
    first_run = True  # Flag para verificar a primeira execução
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
            # Executa imediatamente na primeira execução
            if first_run or current_time - last_run_time >= TIME_CHECK:
                try:
                    trade()
                except Exception as e:
                    logger.error(f"Erro na função trade: {e}")
                last_run_time = current_time  # Atualiza o tempo da última execução
                first_run = False  # Define que a execução inicial já ocorreu
            else:
                # Atraso pequeno para não sobrecarregar o processador
                time.sleep(1)
        else:
            # Atraso enquanto está pausado para evitar loop excessivo
            time.sleep(1)
client = initialize_client(API_KEY, API_SECRET)
conn, c = initialize_database()
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Erro inesperado: {e}")
        input("Pressione qualquer tecla para sair...")  # Mantém a janela aberta para ver o erro
