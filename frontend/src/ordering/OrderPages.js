import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ArrowRight, Check, Coffee, XCircle } from "lucide-react";
import { PageShell } from "./PageShell";
import { api, fmtDate, fmtTime, imgUrl, ORDER_TYPES, rupee, STATUS_LABEL, TRACK_STEPS } from "./shared";

function useOrder(number, poll) {
  const { state } = useLocation();
  const [order, setOrder] = useState(state?.order?.order_number === number ? state.order : null);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    const load = () => api(`/orders/${number}`).then(o => alive && setOrder(o)).catch(e => alive && setError(e.message));
    load();
    const t = poll ? setInterval(load, 5000) : null;
    return () => { alive = false; if (t) clearInterval(t); };
  }, [number, poll]);
  return { order, error };
}

function OrderItems({ order }) {
  return <div className="receipt" data-testid="order-items">
    {order.items.map(i => <div className="receipt-line" key={i.id} data-testid={`order-item-${i.id}`}>
      <div className="cart-thumb">{i.product_image_snapshot ? <img src={imgUrl(i.product_image_snapshot)} alt={i.product_name_snapshot} /> : <Coffee size={16} />}</div>
      <span className="receipt-name">{i.product_name_snapshot} <em>× {i.quantity}</em></span><strong>{rupee(i.subtotal)}</strong>
    </div>)}
    <div className="receipt-total"><span>Subtotal</span><span>{rupee(order.subtotal)}</span></div>
    <div className="receipt-total grand"><span>Total</span><span data-testid="order-total">{rupee(order.total)}</span></div>
  </div>;
}

function Facts({ order, phone }) {
  return <div className="facts">
    <div><small>Order</small><strong data-testid="order-number">{order.order_number}</strong></div>
    <div><small>Name</small><strong data-testid="order-customer">{order.customer_name}</strong></div>
    {phone && <div><small>Phone</small><strong>{order.customer_phone}</strong></div>}
    <div><small>Type</small><strong data-testid="order-type">{ORDER_TYPES[order.order_type]}{order.table_number ? ` · Table ${order.table_number}` : ""}</strong></div>
    <div><small>Placed</small><strong data-testid="order-time">{fmtTime(order.created_at)} · {fmtDate(order.created_at)}</strong></div>
    <div><small>Payment</small><strong>Pay at Café</strong></div>
  </div>;
}

export function OrderConfirmation() {
  const { number } = useParams();
  const { order, error } = useOrder(number.toUpperCase(), false);
  return <PageShell testId="confirmation-page">
    {error && <div className="empty-menu" data-testid="order-error"><span>{error}</span></div>}
    {order && <div className="confirm-wrap">
      <div className="confirm-seal"><Check size={26} /></div>
      <p className="chapter">Order received</p>
      <h1>Your Story <em>Has Begun</em> ✨</h1>
      <p className="order-sub">Order <strong data-testid="confirm-order-number">#{order.order_number}</strong> — your order has been received. We'll start on it right away.</p>
      <div className="paper-card confirm-card"><Facts order={order} /><OrderItems order={order} /></div>
      <div className="confirm-actions">
        <Link to={`/order/${order.order_number}`} className="button dark" data-testid="track-order-button">Track your order <ArrowRight size={15} /></Link>
        <Link to="/#menu" className="text-link" data-testid="back-to-menu-button">Back to Menu <span>↗</span></Link>
      </div>
    </div>}
  </PageShell>;
}

export function OrderTrack() {
  const { number } = useParams();
  const { order, error } = useOrder(number.toUpperCase(), true);
  const idx = order ? TRACK_STEPS.findIndex(s => s.key === order.status) : -1;
  const cancelled = order?.status === "cancelled";
  return <PageShell testId="tracking-page">
    <div className="order-head"><p className="chapter">Chapter 06 <span>— Following Along</span></p><h1>Tracking <em>{number.toUpperCase()}</em></h1>{order && <p className="order-sub">Updates automatically as the café moves your order along.</p>}</div>
    {error && <div className="empty-menu" data-testid="order-error"><span>{error}</span></div>}
    {order && <div className="track-grid">
      <section className="paper-card">
        {cancelled ? <div className="cancelled" data-testid="order-cancelled"><XCircle size={24} /><div><h3>Order cancelled</h3><p>This order was cancelled by the café. Please speak to us at the counter if you have questions.</p></div></div> :
        <ol className="timeline" data-testid="tracking-timeline">{TRACK_STEPS.map((s, i) => <li key={s.key} className={i < idx ? "done" : i === idx ? "current" : ""} data-testid={`track-step-${s.key}`}><span className="dot">{i < idx ? <Check size={12} /> : null}</span><div><strong>{s.title}</strong><p>{s.note}</p></div></li>)}</ol>}
        <p className="status-pill-row">Current status: <span className={`status-pill s-${order.status}`} data-testid="tracking-status">{STATUS_LABEL[order.status]}</span></p>
      </section>
      <section className="paper-card"><Facts order={order} /><OrderItems order={order} /></section>
    </div>}
    <div className="confirm-actions"><Link to="/#menu" className="text-link" data-testid="back-to-menu-button">Back to Menu <span>↗</span></Link></div>
  </PageShell>;
}
