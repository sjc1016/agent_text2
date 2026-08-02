"""B7 循环8：Visitor 创建工单（customer 允许 null，仅记录联系方式）。

验收标准（issue #10）：
  POST /tickets 创建工单（办理类/工单类），Visitor 创建时 customer 允许 null 仅记录联系方式
  （PRD 依据：实现决策 › 工单状态机；CONTEXT › 工单状态机；用户故事 US-13, US-23）

Visitor 无 JWT，工单由助理/坐席在对话流内代建，故本用例走服务层公共 seam
（tool/调度切片复用同一 create_ticket 入口），验证 domain 不变量：customer_id 允许
null、联系方式落库、默认 pending 入队。
"""

import pytest

from app.ticket.service import create_ticket, transition_ticket_status


def test_visitor_ticket_allows_null_customer_with_contact_info(db):
    """Visitor 创建工单：customer_id 为 null，仅记录联系方式（姓名+电话）。"""
    from app.models import Conversation

    conv = Conversation(customer_id=None, status="unauthenticated")
    db.add(conv)
    db.commit()

    ticket = create_ticket(
        db,
        conversation_id=conv.id,
        ticket_type="ticketing",
        content="宽带无法连接，请上门维修",
        creator_type="assistant",
        contact_name="张三",
        contact_phone="13900000001",
    )
    db.commit()
    db.refresh(ticket)

    assert ticket.customer_id is None
    assert ticket.contact_name == "张三"
    assert ticket.contact_phone == "13900000001"
    assert ticket.status.value == "pending"


def test_create_ticket_rejects_unknown_type(db):
    """未知工单类型 → ValueError（服务层守卫，路由层转 422）。"""
    from app.models import Conversation

    conv = Conversation(customer_id=None, status="unauthenticated")
    db.add(conv)
    db.commit()

    with pytest.raises(ValueError):
        create_ticket(
            db,
            conversation_id=conv.id,
            ticket_type="refund",
            content="未知类型",
            creator_type="assistant",
        )


def test_visitor_ticket_state_machine_still_applies(db):
    """Visitor 工单同样走工单类状态机（类型约束，与是否绑定客户无关）。"""
    from app.models import Conversation

    conv = Conversation(customer_id=None, status="unauthenticated")
    db.add(conv)
    db.commit()

    ticket = create_ticket(
        db,
        conversation_id=conv.id,
        ticket_type="ticketing",
        content="宽带故障",
        creator_type="assistant",
        contact_name="李四",
        contact_phone="13900000002",
    )
    db.commit()

    transition_ticket_status(db, ticket, "dispatched")
    db.commit()
    db.refresh(ticket)
    assert ticket.status.value == "dispatched"

    with pytest.raises(ValueError):
        transition_ticket_status(db, ticket, "effective")  # 工单类无 effective


def test_transaction_ticket_state_machine_service_level(db):
    """办理类状态机（服务层）：pending→processing→failed 合法，非法跳转拒绝。"""
    from app.models import Conversation

    conv = Conversation(customer_id=None, status="unauthenticated")
    db.add(conv)
    db.commit()

    ticket = create_ticket(
        db,
        conversation_id=conv.id,
        ticket_type="transaction",
        content="充值缴费",
        creator_type="assistant",
        contact_name="王五",
        contact_phone="13900000003",
    )
    db.commit()

    transition_ticket_status(db, ticket, "processing")
    transition_ticket_status(db, ticket, "failed")
    db.commit()
    db.refresh(ticket)
    assert ticket.status.value == "failed"
