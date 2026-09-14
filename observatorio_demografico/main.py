# ==========================================================
# IMPORTAÇÕES: A PONTE ENTRE PYTHON E NAVEGADOR
# ==========================================================
import pandas as pd  # Biblioteca clássica de ciência de dados. Aqui roda dentro do navegador via WebAssembly.
from pyscript import document, window  # pyright: ignore[reportMissingImports] # 'document' = acesso ao HTML (igual ao JS). 'window' = acesso às APIs globais do navegador.
from pyodide.ffi import create_proxy  # pyright: ignore[reportMissingImports] # "Tradutor": converte funções Python em formato que o JavaScript consegue usar em addEventListener.
import io  # Biblioteca nativa do Python para manipular dados na memória RAM (sem salvar em disco).

# Mensagem de diagnóstico que aparecerá no Console do navegador (F12 → Console)
print("--- Engine de Interatividade Pronto ---")

# ==========================================================
# VARIÁVEL GLOBAL: O CORAÇÃO DOS DADOS
# ==========================================================
# Usamos 'None' para indicar que, no início, ainda não carregamos dados.
# É global porque várias funções (upload, filtro, enter) precisam ler/escrever nela.
df_global = None

# ==========================================================
# FEEDBACK VISUAL INICIAL
# ==========================================================
# Busca no HTML o elemento com id="status-carregamento" (geralmente um <p> ou <div>)
status_block = document.getElementById("status-carregamento")
# Altera o texto visível dentro desse elemento para informar o usuário
status_block.innerText = "✅ Ambiente Python Pronto! Por favor, selecione o arquivo CSV local para iniciar."

# ==========================================================
# FUNÇÃO 1: LEITURA DO ARQUIVO LOCAL (UPLOAD)
# ==========================================================
# 'async' indica que esta função faz uma operação que leva tempo (ler arquivo) 
# e não pode travar a interface enquanto espera.
async def ler_arquivo_local(event):
    """
    Intercepta o upload do arquivo local do usuário e carrega no Pandas.
    """
    # Permite que esta função altere a variável 'df_global' definida fora dela
    global df_global
    
    # event.target é o elemento HTML que disparou o evento (o <input type="file">)
    # .files contém a lista de arquivos selecionados pelo usuário no computador
    arquivos = event.target.files
    
    # Se o usuário cancelou ou não selecionou nada, interrompe a função
    if len(arquivos) == 0:
        return 
    
    # Atualiza a mensagem na tela para indicar que o processamento começou
    status_block.innerText = "⏳ Processando arquivo e extraindo dados demográficos..."

    try:
        # Pega o primeiro arquivo da lista (índice 0)
        js_file = arquivos.item(0)
        
        # Lê o conteúdo do arquivo como ArrayBuffer (formato binário do navegador)
        # 'await' pausa a função até o navegador terminar de ler os bytes do disco
        array_buffer = await js_file.arrayBuffer()
        
        # Converte o objeto JavaScript (ArrayBuffer) para bytes puros do Python
        # .to_py() faz a ponte JS → Python; .tobytes() extrai os dados brutos
        bytes_data = array_buffer.to_py().tobytes()
        
        # Cria um "arquivo virtual" na memória RAM a partir dos bytes
        # pd.read_csv() lê esse arquivo virtual e transforma em DataFrame
        df_global = pd.read_csv(io.BytesIO(bytes_data))
        
        # Atualiza a tela com sucesso e informa quantas linhas foram lidas
        status_block.innerText = f"✅ Sucesso! Base carregada com {len(df_global)} municípios. Pode aplicar os filtros abaixo."
        
        # Chama automaticamente a função de filtro para exibir os dados já carregados
        processar_filtros(event)
        
    except Exception as e:
        # Se der qualquer erro (arquivo corrompido, formato errado, etc.), mostra na tela
        status_block.innerText = f"❌ Erro ao ler o arquivo CSV: {e}"

# ==========================================================
# FUNÇÃO 2: FILTRAGEM E ATUALIZAÇÃO DA INTERFACE
# ==========================================================
def processar_filtros(event):
    """
    Função principal disparada ao clicar no botão ou pressionar Enter.
    Filtra por UF, filtra por nome de município e atualiza TODOS os componentes do DOM.
    """
    # IMPEDE O NAVEGADOR DE RECARREGAR A PÁGINA (comportamento padrão de formulários)
    event.preventDefault()

    global df_global
    # Proteção: se o usuário clicar em "Processar" antes de carregar o CSV, a função para aqui
    if df_global is None:
        print("Erro: O conjunto de dados ainda não foi carregado.")
        return

    # 1. Captura os valores atuais digitados/selecionados nos campos HTML
    uf_selecionada = document.getElementById("filtro-uf").value
    # .strip() remove espaços acidentais; .upper() padroniza para maiúsculas
    termo_busca = document.getElementById("busca-municipio").value.strip().upper()

    print(f"Processando: Filtro UF='{uf_selecionada}' | Busca Cidade='{termo_busca}'")

    # 2. Filtro por Estado (UF)
    # Se o usuário escolheu um estado específico, filtra o DataFrame.
    # Caso contrário, copia o DataFrame inteiro para não modificar o original.
    if uf_selecionada != "TODOS":
        df_filtrado = df_global[df_global["UF"] == uf_selecionada]
    else:
        df_filtrado = df_global.copy()

    # 3. Filtro por Nome do Município (busca parcial, case-insensitive)
    if termo_busca:
        # .str.upper().str.contains() verifica se o termo digitado existe dentro do nome da cidade
        df_filtrado = df_filtrado[df_filtrado["NOME DO MUNICÍPIO"].str.upper().str.contains(termo_busca)]

    # 4. Cálculos de totais APENAS sobre os dados filtrados
    # .sum() soma toda a coluna; pandas ignora valores nulos automaticamente
    total_coletado = df_filtrado["POP. COLETADA"].sum()
    total_imputado = df_filtrado["POP. IMPUTADA"].sum()
    total_geral = df_filtrado["POP. TOTAL"].sum()

    # 5. Atualização dos 3 Cards de Métricas no HTML
    # : , formata o número adicionando separadores de milhar (ex: 1,234,567)
    document.getElementById("card-coletada").innerText = f"{total_coletado:,}"
    document.getElementById("card-imputada").innerText = f"{total_imputado:,}"
    document.getElementById("card-total").innerText = f"{total_geral:,}"

    # 6. Atualização Dinâmica da Tabela
    tbody_tabela = document.getElementById("dados-municipios")
    tbody_tabela.innerHTML = ""  # Limpa completamente as linhas antigas antes de inserir as novas

    # Se nenhum registro passou pelos filtros, mostra mensagem amigável e para a execução
    if len(df_filtrado) == 0:
        tbody_tabela.innerHTML = "<tr><td colspan='6' style='text-align:center;'>Nenhum município encontrado com os filtros aplicados.</td></tr>"
        return

    # OTIMIZAÇÃO: Limita a 50 linhas para não travar o navegador com milhares de <tr>
    df_visualizacao = df_filtrado.head(50)

    # Monta uma string gigante com todo o HTML das linhas da tabela
    linhas_html = ""
    for _, linha in df_visualizacao.iterrows():
        # f-string do Python + quebra de linha tripla para legibilidade
        # int() converte floats do pandas para inteiros limpos; :, formata com separadores
        linhas_html += f"""
        <tr>
            <td>{linha['UF']}</td>
            <td>{linha['COD. MUNIC']}</td>
            <td>{linha['NOME DO MUNICÍPIO']}</td>
            <td>{int(linha['POP. COLETADA']):,}</td>
            <td>{int(linha['POP. IMPUTADA']):,}</td>
            <td>{int(linha['POP. TOTAL']):,}</td>
        </tr>
        """
    
    # Injeta a string HTML pronta direto no <tbody> da tabela
    # O navegador renderiza instantaneamente sem recarregar a página
    tbody_tabela.innerHTML = linhas_html
    print(f"Interface atualizada com sucesso! {len(df_filtrado)} registros processados.")

# ==========================================================
# FUNÇÃO 3: DETECÇÃO DA TECLA ENTER
# ==========================================================
def detectar_enter(event):
    # Garante que estamos trabalhando com o objeto de evento nativo do JavaScript
    js_event = event.to_js() if hasattr(event, "to_js") else event
    
    # Lê qual tecla foi pressionada. Se for "Enter", executa o filtro
    if getattr(js_event, "key", None) == "Enter":
        event.preventDefault()  # Evita que o formulário envie/recarregue
        processar_filtros(event)  # Reutiliza a lógica de filtragem já escrita

# ==========================================================
# 🔌 A PONTE DE EVENTOS: CONECTANDO PYTHON AO DOM
# ==========================================================
# O método addEventListener de um elemento HTML é um método nativo do JavaScript
# O JavaScript não consegue chamar funções Python diretamente.
# create_proxy() "embrulha" a função Python em um objeto que o método addEventListener entende.
proxy_filtro = create_proxy(processar_filtros)
proxy_teclado = create_proxy(detectar_enter)
proxy_upload = create_proxy(ler_arquivo_local)

# 1. Quando clicar no botão, executa a filtragem
document.getElementById("btn-processar").addEventListener("click", proxy_filtro)

# 2. Quando digitar no campo de busca, monitora teclas (para capturar o Enter)
document.getElementById("busca-municipio").addEventListener("keydown", proxy_teclado)

# 3. Quando o usuário selecionar um arquivo no input, dispara a leitura assíncrona
document.getElementById("upload-csv").addEventListener("change", proxy_upload)