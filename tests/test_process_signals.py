"""
Testes unitários para o barramento de sinais em tempo real (SignalTracker).
"""
import pytest
from src.core.process_signals import SignalTracker, init_signals_table
from src.core.database import get_db

def test_signal_tracker_lifecycle():
    init_signals_table()

    # 1. Início de processo
    SignalTracker.emit_start(
        "test_worker",
        "Tarefa de Teste",
        total_steps=4,
        message="Iniciando teste"
    )

    signals = SignalTracker.get_all_signals()
    worker_sig = next((s for s in signals if s["process_name"] == "test_worker"), None)
    assert worker_sig is not None
    assert worker_sig["status"] == "RUNNING"
    assert worker_sig["current_step"] == 0
    assert worker_sig["total_steps"] == 4

    # 2. Progresso
    SignalTracker.emit_progress(
        "test_worker",
        current_step=2,
        total_steps=4,
        message="Etapa 2 em andamento"
    )

    signals = SignalTracker.get_all_signals()
    worker_sig = next((s for s in signals if s["process_name"] == "test_worker"), None)
    assert worker_sig["current_step"] == 2
    assert worker_sig["message"] == "Etapa 2 em andamento"

    # 3. Conclusão
    SignalTracker.emit_finish(
        "test_worker",
        message="Teste finalizado com êxito",
        success=True,
        metadata={"metric": 100}
    )

    signals = SignalTracker.get_all_signals()
    worker_sig = next((s for s in signals if s["process_name"] == "test_worker"), None)
    assert worker_sig["status"] == "COMPLETED"
    assert worker_sig["extra"].get("metric") == 100

def test_signal_tracker_failure():
    init_signals_table()

    SignalTracker.emit_start("test_fail", "Tarefa Falha", total_steps=2)
    SignalTracker.emit_finish("test_fail", message="Ocorreu um erro no teste", success=False)

    signals = SignalTracker.get_all_signals()
    fail_sig = next((s for s in signals if s["process_name"] == "test_fail"), None)
    assert fail_sig is not None
    assert fail_sig["status"] == "FAILED"
    assert "erro" in fail_sig["message"].lower()
