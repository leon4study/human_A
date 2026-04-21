import "./equipment-modal.css";

interface AiAnalysisModalProps {
  open: boolean;
  onClose: () => void;
}

function AiAnalysisModal({ open, onClose }: AiAnalysisModalProps) {
  if (!open) return null;

  return (
    <div className="equipment-modal-overlay" onClick={onClose}>
      <div className="equipment-modal" onClick={(e) => e.stopPropagation()}>
        <div className="equipment-modal-header">
          <div>
            <div className="equipment-modal-title">AI 분석 결과</div>
            <div className="equipment-modal-subtitle">AI 기반 설비 이상 분석</div>
          </div>

          <button className="equipment-modal-close" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="equipment-modal-body">
          <div className="equipment-modal-section">
            <div className="equipment-modal-section-title">분석 내용</div>
            <div className="equipment-modal-row">
              <span className="equipment-modal-label">준비 중</span>
              <span className="equipment-modal-value">내용이 추가될 예정입니다.</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default AiAnalysisModal;
