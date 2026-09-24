# Genera las figuras del deck y lo compila con panduck.
PREPARAR := preparar-figuras.py

main.pdf: main.md head.yaml img
	panduck build -p slides

img: $(PREPARAR) pantalla.png
	cd ../.. && uv run --with segno python slides/frogql-evento/preparar-figuras.py
	@touch img

.PHONY: figuras clean
figuras:
	cd ../.. && uv run --with segno python slides/frogql-evento/preparar-figuras.py

clean:
	rm -rf img main.typ main.pdf _dot_*.svg
