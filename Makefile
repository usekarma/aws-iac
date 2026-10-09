.PHONY: validate test verify demo
validate:
	./scripts/verify.sh

test:
	PYTHONPATH=scripts python3 -m unittest discover -s tests -v

verify: validate

demo:
	python3 scripts/demo.py
