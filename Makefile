.PHONY: test run restart health metrics

test:
	python3 -m unittest discover -s tests -v

run:
	python3 plot_butler.py

restart:
	sudo systemctl restart plot-butler.service

health:
	curl -sS http://127.0.0.1:8088/api/health | python3 -m json.tool

metrics:
	curl -sS http://127.0.0.1:8088/api/metrics
