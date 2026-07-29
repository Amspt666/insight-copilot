.PHONY: setup start eval eval-ablation test demo-data

setup:        ## 一键配置（依赖+数据库）
	bash setup.sh

start:        ## 启动服务（http://localhost:8000）
	bash start.sh

eval:         ## 完整管线评测（100 题，需先在 .env 配置 Key）
	cd backend && python3 -m eval.run_eval --config full

eval-ablation:## 基线 + 消融评测
	cd backend && python3 -m eval.run_eval --config baseline --skip-insight
	cd backend && python3 -m eval.run_eval --config no_semantic --categories A,B,C --skip-insight
	cd backend && python3 -m eval.run_eval --config no_repair --categories A,B,C --skip-insight
	cd backend && python3 -m eval.run_eval --config no_clarify --categories D,E --skip-insight

test:         ## 机制级单元测试（校验器/沙箱/数字溯源）
	cd backend && python3 -m pytest tests/ -q

demo-data:    ## 重新生成前端内置演示数据
	python3 scripts/gen_demo_data.py frontend/src/lib
