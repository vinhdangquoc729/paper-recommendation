import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { PaperLink } from "../components/PaperLink";
import { authorsShort, decisionLabel } from "../format";
import type { AuthoredPaper, Meta, Preferences, Profile } from "../types";
import { useAsync } from "../useAsync";

/** Tài khoản: thông tin cá nhân, OpenReview ID để nhận diện bài đã đăng, và sở thích. */
export function AccountPage({ meta }: { meta: Meta | null }) {
  const me = useAsync(() => api.me(), []);
  const [form, setForm] = useState<Profile | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [authoredKey, setAuthoredKey] = useState(0);   // tăng lên để tải lại danh sách bài của tôi

  useEffect(() => {
    if (me.data) setForm(me.data);
  }, [me.data]);

  const authored = useAsync(() => api.authored(), [authoredKey]);
  const saved = useAsync(() => api.saved(), []);

  if (me.error) return <p className="error">{me.error}</p>;
  if (!form) return <p className="muted">Đang tải...</p>;

  const setPref = <K extends keyof Preferences>(key: K, value: Preferences[K]) =>
    setForm({ ...form, preferences: { ...form.preferences, [key]: value } });

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const idChanged = form.openreview_id.trim() !== (me.data?.openreview_id ?? "");
      const res = await api.saveMe(form);
      me.setData(res);
      setSavedAt(new Date().toLocaleTimeString("vi-VN"));
      if (idChanged) setAuthoredKey((k) => k + 1);
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <h1>Tài khoản</h1>
      <p className="muted">
        Thông tin ở đây được dùng để dựng hồ sơ gợi ý trên trang <Link to="/">Bài báo</Link>.
      </p>

      <fieldset>
        <legend>Thông tin cá nhân</legend>
        <div className="form-grid">
          <label htmlFor="name">Tên hiển thị</label>
          <input id="name" type="text" value={form.display_name}
                 onChange={(e) => setForm({ ...form, display_name: e.target.value })} />

          <label htmlFor="email">Email</label>
          <input id="email" type="email" value={form.email}
                 onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <div className="hint">Không bắt buộc. Dùng để gửi bản tin gợi ý hằng tuần sau này.</div>

          <label htmlFor="orid">OpenReview ID</label>
          <input id="orid" type="text" value={form.openreview_id} placeholder="~Nguyen_Van_A1"
                 onChange={(e) => setForm({ ...form, openreview_id: e.target.value })} />
          <div className="hint">
            Lấy trong đường dẫn hồ sơ OpenReview của bạn, ví dụ openreview.net/profile?id=~Nguyen_Van_A1.
            Hệ thống dùng ID này để tìm các bài bạn đã công khai.
          </div>
        </div>
      </fieldset>

      <fieldset>
        <legend>Bài báo của bạn trên OpenReview</legend>
        <AuthoredTable openreviewId={me.data?.openreview_id ?? ""} rows={authored.data} loading={authored.loading}
                       error={authored.error} />
      </fieldset>

      <PreferencesForm prefs={form.preferences} meta={meta} setPref={setPref} />

      <div className="savebar">
        <button className="primary" onClick={save} disabled={saving}>{saving ? "Đang lưu..." : "Lưu thay đổi"}</button>
        {savedAt && !saveError && <span className="muted small">Đã lưu lúc {savedAt}</span>}
        {saveError && <span className="small" style={{ color: "var(--danger)" }}>{saveError}</span>}
      </div>

      <h2>Bài đã lưu</h2>
      {saved.data && saved.data.length === 0 && (
        <p className="muted">Chưa có bài nào. Bấm "Lưu" ở một bài để thêm vào đây.</p>
      )}
      {saved.data && saved.data.length > 0 && (
        <table className="grid">
          <thead><tr><th>Bài báo</th><th>Hội nghị</th><th>Kết quả</th></tr></thead>
          <tbody>
            {saved.data.map((p) => (
              <tr key={p.id}>
                <td><PaperLink paper={p} /></td>
                <td style={{ whiteSpace: "nowrap" }}>{p.venue} {p.year}</td>
                <td>{decisionLabel(p.decision)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function AuthoredTable({ openreviewId, rows, loading, error }: {
  openreviewId: string; rows: AuthoredPaper[] | null; loading: boolean; error: string | null;
}) {
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  useEffect(() => {
    setConfirmed(Object.fromEntries((rows ?? []).map((r) => [r.paper.id, r.confirmed])));
  }, [rows]);

  if (!openreviewId) return <p className="muted small">Nhập OpenReview ID rồi bấm "Lưu thay đổi" để tìm bài của bạn.</p>;
  if (error) return <p className="error">{error}</p>;
  if (loading || !rows) return <p className="muted">Đang tìm bài...</p>;
  if (rows.length === 0) {
    return <p className="muted small">Không tìm thấy bài nào của {openreviewId} trong dữ liệu hiện có.</p>;
  }

  const toggle = async (id: string, value: boolean) => {
    setConfirmed((c) => ({ ...c, [id]: value }));
    try {
      await api.confirmAuthored(id, value);
    } catch {
      setConfirmed((c) => ({ ...c, [id]: !value }));
    }
  };

  return (
    <>
      <p className="small muted" style={{ marginTop: 0 }}>
        Tìm thấy {rows.length} bài. Bỏ đánh dấu những bài không phải của bạn; bài được đánh dấu sẽ dùng để dựng hồ sơ.
      </p>
      <table className="grid">
        <thead>
          <tr><th className="center">Của tôi</th><th>Bài báo</th><th>Hội nghị</th><th>Kết quả</th></tr>
        </thead>
        <tbody>
          {rows.map(({ paper }) => (
            <tr key={paper.id}>
              <td className="center">
                <input type="checkbox" checked={confirmed[paper.id] ?? true}
                       onChange={(e) => toggle(paper.id, e.target.checked)}
                       aria-label={`Bài ${paper.title} là của tôi`} />
              </td>
              <td>
                <PaperLink paper={paper} />
                <div className="small muted">{authorsShort(paper.authors, 5)}</div>
              </td>
              <td style={{ whiteSpace: "nowrap" }}>{paper.venue} {paper.year}</td>
              <td>{decisionLabel(paper.decision)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function PreferencesForm({ prefs, meta, setPref }: {
  prefs: Preferences; meta: Meta | null;
  setPref: <K extends keyof Preferences>(key: K, value: Preferences[K]) => void;
}) {
  const [areaFilter, setAreaFilter] = useState("");
  const areas = useMemo(() => {
    const f = areaFilter.trim().toLowerCase();
    return (meta?.areas ?? []).filter((a) => !f || a.label.toLowerCase().includes(f) || prefs.areas.includes(a.value));
  }, [meta, areaFilter, prefs.areas]);

  const toggleIn = (list: string[], value: string, on: boolean) =>
    on ? [...list, value] : list.filter((x) => x !== value);

  return (
    <fieldset>
      <legend>Sở thích</legend>
      <div className="form-grid">
        <label>Lĩnh vực quan tâm</label>
        <div>
          <input type="search" placeholder="Lọc danh sách lĩnh vực" value={areaFilter}
                 onChange={(e) => setAreaFilter(e.target.value)} style={{ width: "100%", marginBottom: 4 }} />
          <div className="checklist">
            {areas.map((a) => (
              <label key={a.value}>
                <input type="checkbox" checked={prefs.areas.includes(a.value)}
                       onChange={(e) => setPref("areas", toggleIn(prefs.areas, a.value, e.target.checked))} />{" "}
                {a.label} <span className="count">({a.count.toLocaleString("vi-VN")})</span>
              </label>
            ))}
          </div>
          <div className="small muted">Đã chọn {prefs.areas.length} lĩnh vực.</div>
        </div>

        <label>Hội nghị</label>
        <div>
          {meta?.venues.map((v) => (
            <label key={v.value} style={{ marginRight: 16 }}>
              <input type="checkbox" checked={prefs.venues.includes(v.value)}
                     onChange={(e) => setPref("venues", toggleIn(prefs.venues, v.value, e.target.checked))} />{" "}
              {v.label}
            </label>
          ))}
        </div>
        <div className="hint">Không chọn hội nghị nào nghĩa là lấy tất cả.</div>

        <label htmlFor="kw">Từ khoá</label>
        <input id="kw" type="text" value={prefs.keywords.join(", ")} placeholder="ví dụ: diffusion, graph neural network"
               onChange={(e) => setPref("keywords", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />
        <div className="hint">Cách nhau bằng dấu phẩy.</div>

        <label htmlFor="year">Chỉ lấy bài từ năm</label>
        <select id="year" value={prefs.year_from ?? ""}
                onChange={(e) => setPref("year_from", e.target.value ? Number(e.target.value) : null)}
                style={{ width: 140 }}>
          <option value="">Không giới hạn</option>
          {meta?.years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>

        <label>Tuỳ chọn</label>
        <div>
          <label style={{ display: "block" }}>
            <input type="checkbox" checked={prefs.include_rejected}
                   onChange={(e) => setPref("include_rejected", e.target.checked)} />{" "}
            Gợi ý cả bài bị từ chối (vẫn có review công khai)
          </label>
          <label style={{ display: "block" }}>
            <input type="checkbox" checked={prefs.only_with_code}
                   onChange={(e) => setPref("only_with_code", e.target.checked)} />{" "}
            Chỉ gợi ý bài có mã nguồn
          </label>
        </div>

        <label>Độ mới</label>
        <div className="slider">
          <span>Kinh điển</span>
          <input type="range" min={0} max={1} step={0.1} value={prefs.freshness}
                 onChange={(e) => setPref("freshness", Number(e.target.value))} aria-label="Độ mới" />
          <span>Mới nhất</span>
        </div>

        <label>Độ đa dạng</label>
        <div className="slider">
          <span>Sát chủ đề</span>
          <input type="range" min={0} max={1} step={0.1} value={prefs.diversity}
                 onChange={(e) => setPref("diversity", Number(e.target.value))} aria-label="Độ đa dạng" />
          <span>Đa dạng</span>
        </div>
      </div>
    </fieldset>
  );
}
