"""Teste automatico do registro de solicitacao de resgate.

Roda o fluxo sozinho (sem digitar nada):
  1. Cria uma imagem de teste e registra a foto (valida + copia).
  2. Monta uma solicitacao de resgate com dados de exemplo.
  3. Salva no JSON.
  4. Rele o JSON e confere que todos os campos bateram.
  5. Testa tambem a validacao (foto inexistente / extensao invalida).

Rode com:  py test_registro.py
"""

from __future__ import annotations

import json

import main


def checar(condicao: bool, mensagem: str) -> None:
    if not condicao:
        raise AssertionError(mensagem)
    print(f"  [OK] {mensagem}")


def teste_fluxo_completo() -> None:
    print("\n== Teste: fluxo completo de registro ==")

    # 1. Cria uma imagem de teste (um .png minimo de 1x1 pixel).
    pixel_png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c6360000002000154a24f3b0000000049454e44ae426082"
    )
    main.PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    foto_teste = main.PASTA_DADOS / "foto_teste.png"
    foto_teste.write_bytes(pixel_png)

    # 2. Registra a foto (deve validar e copiar para data/photos).
    foto_path = main.registrar_foto(str(foto_teste))
    from pathlib import Path
    checar(Path(foto_path).is_file(), "foto foi copiada para a pasta do projeto")
    checar("photos" in foto_path, "foto foi salva dentro de data/photos")

    # 3. Monta a solicitacao com dados de exemplo (com coordenadas exatas).
    solicitacao = main.montar_solicitacao(
        nome="Maria Silva",
        contato="maria@email.com",
        endereco="Av. Paulista, 1000 - Sao Paulo",
        latitude=-23.5505,
        longitude=-46.6333,
        especie="cachorro",
        porte="medio",
        estado_saude="ferido na pata",
        descricao="Cachorro assustado embaixo de um carro.",
        urgencia="alta",
        foto_path=foto_path,
    )

    # 4. Salva no JSON.
    main.salvar(solicitacao)

    # 5. Rele o JSON e confere.
    lista = json.loads(main.ARQUIVO_JSON.read_text(encoding="utf-8"))
    checar(len(lista) >= 1, "arquivo JSON tem ao menos 1 solicitacao")

    salva = lista[-1]  # a ultima e a que acabamos de salvar
    checar(salva["id"] == solicitacao["id"], "id foi persistido corretamente")
    checar(salva["status"] == "aberto", "status inicial e 'aberto'")
    checar(salva["solicitante"]["nome"] == "Maria Silva", "nome do solicitante bateu")
    checar(salva["solicitante"]["contato"] == "maria@email.com", "contato bateu")
    checar(
        salva["localizacao"]["endereco"] == "Av. Paulista, 1000 - Sao Paulo",
        "endereco foi persistido",
    )
    checar(salva["localizacao"]["latitude"] == -23.5505, "latitude bateu")
    checar(salva["localizacao"]["longitude"] == -46.6333, "longitude bateu")
    checar(
        salva["localizacao"]["mapa_url"]
        == "https://www.google.com/maps?q=-23.5505,-46.6333",
        "link do mapa por coordenadas foi gerado corretamente",
    )
    checar(salva["animal"]["especie"] == "cachorro", "especie bateu")
    checar(salva["animal"]["urgencia"] == "alta", "urgencia bateu")
    checar(salva["foto_path"] == foto_path, "caminho da foto foi persistido")
    checar("criado_em" in salva and salva["criado_em"], "data/hora foi registrada")


def teste_mapa_por_endereco() -> None:
    print("\n== Teste: link do mapa so com endereco (sem coordenadas) ==")

    # Sem coordenadas, o link deve ser uma BUSCA pelo endereco.
    url = main.montar_mapa_url("Av. Paulista, 1000 - Sao Paulo")
    checar("google.com/maps/search" in url, "usa a busca do Google Maps")
    checar("Av.+Paulista" in url or "Av.%20Paulista" in url, "endereco foi codificado na URL")

    # Montando uma solicitacao so com endereco (lat/lon None).
    pedido = main.montar_solicitacao(
        nome="Joao",
        contato="11 99999-0000",
        endereco="Rua das Flores, 50 - Centro",
        especie="gato",
        porte="pequeno",
        estado_saude="ok",
        descricao="Gato preso no telhado.",
        urgencia="media",
    )
    checar(pedido["localizacao"]["latitude"] is None, "latitude fica None sem coordenadas")
    checar(pedido["localizacao"]["longitude"] is None, "longitude fica None sem coordenadas")
    checar(
        "search" in pedido["localizacao"]["mapa_url"],
        "link do mapa cai na busca por endereco",
    )


def teste_validacao_foto() -> None:
    print("\n== Teste: validacao da foto ==")

    # Foto que nao existe deve dar erro.
    try:
        main.registrar_foto("arquivo_que_nao_existe.png")
        raise AssertionError("deveria ter falhado com arquivo inexistente")
    except ValueError:
        print("  [OK] foto inexistente foi rejeitada")

    # Extensao invalida deve dar erro.
    arquivo_txt = main.PASTA_DADOS / "nao_e_imagem.txt"
    arquivo_txt.write_text("isto nao e uma imagem", encoding="utf-8")
    try:
        main.registrar_foto(str(arquivo_txt))
        raise AssertionError("deveria ter falhado com extensao invalida")
    except ValueError:
        print("  [OK] extensao de arquivo invalida foi rejeitada")


if __name__ == "__main__":
    teste_fluxo_completo()
    teste_mapa_por_endereco()
    teste_validacao_foto()
    print("\n==============================")
    print("  TODOS OS TESTES PASSARAM")
    print("==============================")
