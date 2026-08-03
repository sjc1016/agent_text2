"""客户侧数据契约（issue #53 B13）：/customers/me + /notifications。

客户侧只读端点（CurrentCustomer 守卫），解除 UI-C-4（#16）/ UI-C-5（#11）
的 mock 兜底（TODO(backend) 标注替换）。
"""

from app.customers.routes import router

__all__ = ["router"]
