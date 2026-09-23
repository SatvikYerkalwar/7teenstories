import { useCallback, useEffect, useRef, useState } from "react";
import { Bell, BellRing, Coffee, MessageSquare, X } from "lucide-react";
import { api, fmtDate, fmtTime, imgUrl, ORDER_TYPES, post, rupee, STATUS_LABEL, STATUSES } from "./shared";

function chime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [523, 659, 784].forEach((f, i) => { const o = ctx.createOscillator(), g = ctx.createGain(); o.connect(g); g.connect(ctx.destination); o.frequency.value = f; g.gain.setValueAtTime(0.0001, ctx.currentTime + i * 0.16); g.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + i * 0.16 + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + i * 0.16 + 0.35); o.start(ctx.currentTime + i * 0.16); o.stop(ctx.currentTime + i * 0.16 + 0.4); });
  } catch {}
}

export function useOrdersFeed() {
  const [orders, setOrders] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const known = useRef(null);
  const load = useCallback(async () => {
    const list = await api("/admin/orders");
    setOrders(list);
    if (known.current) {
      const fresh = list.filter(o => !known.current.has(o.id));
      if (fresh.length) {
        setAlerts(a => [...fresh, ...a].slice(0, 5)); chime();
        if ("Notification" in window && Notification.permission === "granted") fresh.forEach(o => new Notification(`New order ${o.order_number}`, { body: `${rupee(o.total)} · ${ORDER_TYPES[o.order_type]} · ${o.customer_name}` }));
      }
    }
    known.current = new Set(list.map(o => o.id));
  }, []);
  useEffect(() => { load().catch(() => {}); const t = setInterval(() => load().catch(() => {}), 5000); return () => clearInterval(t); }, [load]);
  const setStatus = async (id, status) => { await post(`/admin/orders/${id}/status`, { status }, "PATCH"); await load(); };
  const dismiss = id => setAlerts(a => a.filter(o => o.id !== id));
  return { orders, alerts, dismiss, setStatus, reload: load };
}

export function NewOrderAlerts({ alerts, onView, onDismiss }) {
  if (!alerts.length) return null;
  return <div className="alert-stack" data-testid="new-order-alerts">{alerts.map(o => <div className="order-alert" key={o.id} data-testid={`new-order-alert-${o.id}`}>
    <BellRing size={18} /><div><strong>New Order Received</strong><span>Order #{o.order_number} · {rupee(o.total)} · {ORDER_TYPES[o.order_type]}</span></div>
    <button className="button dark" onClick={() => onView(o)} data-testid={`alert-view-${o.id}`}>View Order</button>
    <button className="icon-btn" onClick={() => onDismiss(o.id)} aria-label="Dismiss" data-testid={`alert-dismiss-${o.id}`}><X size={16} /></button>
  </div>)}</div>;
}

export function NotifyToggle() {
  const [perm, setPerm] = useState(typeof Notification !== "undefined" ? Notification.permission : "unsupported");
  if (perm !== "default") return null;
  return <button className="button light" onClick={() => Notification.requestPermission().then(setPerm)} data-testid="enable-notifications-button"><Bell size={15} /> Enable browser alerts</button>;
}

const isToday = iso => new Date(iso).toDateString() === new Date().toDateString();

export function DashboardPanel({ orders, onOpen }) {
  const today = orders.filter(o => isToday(o.created_at));
  const active = orders.filter(o => ["new", "accepted", "preparing", "ready"].includes(o.status));
  const revenue = today.filter(o => o.status !== "cancelled").reduce((s, o) => s + o.total, 0);
  return <div data-testid="dashboard-panel">
    <div className="stats order-stats"><div><span>Orders today</span><strong data-testid="stat-orders-today">{today.length}</strong></div><div><span>Active orders</span><strong data-testid="stat-active-orders">{active.length}</strong></div><div><span>New (unaccepted)</span><strong data-testid="stat-new-orders">{orders.filter(o => o.status === "new").length}</strong></div><div><span>Today's sales</span><strong data-testid="stat-revenue">{rupee(revenue)}</strong></div></div>
    <div className="table-head"><div><h2>Live orders</h2><p>What's on the counter right now. Tap an order to update its status.</p></div><NotifyToggle /></div>
    {active.length ? <div className="order-cards">{active.map(o => <button className={`order-card s-${o.status}`} key={o.id} onClick={() => onOpen(o)} data-testid={`live-order-${o.id}`}><div className="order-card-top"><strong>{o.order_number}</strong><span className={`status-pill s-${o.status}`}>{STATUS_LABEL[o.status]}</span></div><p>{o.customer_name} · {ORDER_TYPES[o.order_type]}{o.table_number ? ` · T${o.table_number}` : ""}</p><small>{o.items.map(i => `${i.product_name_snapshot} × ${i.quantity}`).join(", ")}</small><div className="order-card-foot"><span>{fmtTime(o.created_at)}</span><strong>{rupee(o.total)}</strong></div></button>)}</div>
    : <div className="empty-admin" data-testid="no-live-orders">No live orders right now. New orders will appear here instantly.</div>}
  </div>;
}

export function OrdersPanel({ orders, onOpen }) {
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const shown = orders.filter(o => (filter === "all" || (filter === "active" ? ["new", "accepted", "preparing", "ready"].includes(o.status) : o.status === filter)) && (o.order_number + o.customer_name + o.customer_phone).toLowerCase().includes(search.toLowerCase()));
  return <div data-testid="orders-panel">
    <div className="table-head"><div><h2>Orders</h2><p>Every order ever placed — live queue and history in one place.</p></div></div>
    <div className="toolbar orders-toolbar"><div className="search"><input placeholder="Search order #, name or phone…" value={search} onChange={e => setSearch(e.target.value)} data-testid="order-search-input" /></div>
      <div className="chip-row">{["all", "active", ...STATUSES].map(s => <button key={s} className={`chip ${filter === s ? "active" : ""}`} onClick={() => setFilter(s)} data-testid={`order-filter-${s}`}>{s === "all" ? "All" : s === "active" ? "Active" : STATUS_LABEL[s]}</button>)}</div></div>
    <div className="admin-table orders-table"><div className="table-row order-row table-label"><span>Order</span><span>Customer</span><span>Type</span><span>Total</span><span>Status</span><span>Time</span></div>
      {shown.map(o => <button className="table-row order-row" key={o.id} onClick={() => onOpen(o)} data-testid={`order-row-${o.id}`}><strong>{o.order_number}</strong><span>{o.customer_name}</span><span>{ORDER_TYPES[o.order_type]}{o.table_number ? ` · T${o.table_number}` : ""}</span><span>{rupee(o.total)}</span><span className={`status-pill s-${o.status}`}>{STATUS_LABEL[o.status]}</span><span>{fmtTime(o.created_at)}<small>{isToday(o.created_at) ? "Today" : fmtDate(o.created_at)}</small></span></button>)}
    </div>
    {!shown.length && <div className="empty-admin" data-testid="no-orders">No orders match this view yet.</div>}
  </div>;
}

export function OrderDetail({ order, onClose, onStatus }) {
  const [busy, setBusy] = useState(false);
  useEffect(() => { const k = e => e.key === "Escape" && onClose(); window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, [onClose]);
  const change = async e => { setBusy(true); try { await onStatus(order.id, e.target.value); } catch (err) { alert(err.message); } finally { setBusy(false); } };
  return <div className="modal-backdrop" onClick={onClose}><div className="modal order-modal" onClick={e => e.stopPropagation()} data-testid="order-detail-modal">
    <div className="modal-head"><div><p className="chapter">Order details</p><h2>Order <em>#{order.order_number}</em></h2></div><button className="icon-btn" onClick={onClose} aria-label="Close" data-testid="order-detail-close"><X /></button></div>
    <div className="facts admin-facts">
      <div><small>Customer</small><strong data-testid="detail-customer">{order.customer_name}</strong></div>
      <div><small>Phone</small><strong data-testid="detail-phone"><a href={`tel:${order.customer_phone}`}>{order.customer_phone}</a></strong></div>
      <div><small>Order type</small><strong data-testid="detail-type">{ORDER_TYPES[order.order_type]}{order.table_number ? ` · Table ${order.table_number}` : ""}</strong></div>
      <div><small>Placed</small><strong>{fmtTime(order.created_at)} · {fmtDate(order.created_at)}</strong></div>
      <div><small>Payment</small><strong>Pay at Café · {order.payment_status}</strong></div>
      <div><small>Status</small><select value={order.status} onChange={change} disabled={busy} className={`status-select s-${order.status}`} data-testid="order-status-select">{STATUSES.map(s => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}</select></div>
    </div>
    <h3 className="items-title">Items</h3>
    <div className="receipt">{order.items.map(i => <div className="receipt-line" key={i.id} data-testid={`detail-item-${i.id}`}><div className="cart-thumb">{i.product_image_snapshot ? <img src={imgUrl(i.product_image_snapshot)} alt="" /> : <Coffee size={14} />}</div><span className="receipt-name">{i.product_name_snapshot} <em>× {i.quantity}</em></span><strong>{rupee(i.subtotal)}</strong></div>)}
      <div className="receipt-total grand"><span>Total</span><span data-testid="detail-total">{rupee(order.total)}</span></div></div>
    <div className="status-steps">{STATUSES.filter(s => s !== "cancelled").map(s => <button key={s} className={`chip ${order.status === s ? "active" : ""}`} disabled={busy} onClick={() => change({ target: { value: s } })} data-testid={`status-btn-${s}`}>{STATUS_LABEL[s]}</button>)}<button className={`chip danger ${order.status === "cancelled" ? "active" : ""}`} disabled={busy} onClick={() => window.confirm("Cancel this order?") && change({ target: { value: "cancelled" } })} data-testid="status-btn-cancelled">Cancelled</button></div>
    <SmsNote order={order} />
  </div></div>;
}

function SmsNote({ order }) {
  const [configured, setConfigured] = useState(null);
  useEffect(() => { api("/admin/settings").then(s => setConfigured(s.sms_configured)).catch(() => setConfigured(false)); }, []);
  if (order.ready_sms_status === "sent") return <p className="sms-note sent" data-testid="sms-status"><MessageSquare size={13} /> "Order ready" SMS sent to {order.customer_phone} at {fmtTime(order.ready_sms_sent_at)}</p>;
  if (order.ready_sms_status === "failed") return <p className="sms-note failed" data-testid="sms-status"><MessageSquare size={13} /> SMS could not be sent — {order.ready_sms_detail}</p>;
  if (configured === false) return <p className="sms-note" data-testid="sms-status"><MessageSquare size={13} /> Ready-SMS is off: add Twilio credentials to enable customer texts</p>;
  if (configured) return <p className="sms-note" data-testid="sms-status"><MessageSquare size={13} /> Customer will get an SMS when marked Ready</p>;
  return null;
}
