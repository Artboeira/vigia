"""Ícone do app: símbolo AB em bone sobre ink, 1024 px. Só no build (precisa de Pillow).

Uso: python packaging/make_icon.py <saida.png>
"""
import os
import sys

from PIL import Image

SIZE = 1024
INK = (0x22, 0x22, 0x23, 255)

here = os.path.dirname(os.path.abspath(__file__))
symbol = Image.open(os.path.join(here, "symbol_bone.png")).convert("RGBA")
symbol = symbol.crop(symbol.getchannel("A").getbbox())
k = SIZE * 0.62 / max(symbol.size)
symbol = symbol.resize((round(symbol.width * k), round(symbol.height * k)), Image.LANCZOS)
icon = Image.new("RGBA", (SIZE, SIZE), INK)
icon.alpha_composite(symbol, ((SIZE - symbol.width) // 2, (SIZE - symbol.height) // 2))
icon.save(sys.argv[1])
