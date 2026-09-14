# Genera las figuras del deck y lo compila con panduck.
FUENTE := ../figuras-slides.py

main.pdf: main.md head.yaml img
	panduck build -p slides

img: $(FUENTE)
	cd ../.. && uv run python slides/figuras-slides.py
	@touch img

.PHONY: figuras clean
figuras:
	cd ../.. && uv run python slides/figuras-slides.py

clean:
	rm -rf img main.typ main.pdf _dot_*.svg
