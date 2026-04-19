import type { Equipment } from "../center/facility/facilityTypes";
import "./equipment-modal.css";

interface EquipmentModalProps {
  equipment: Equipment | null;   // 현재 선택된 장비
  onClose: () => void;   // 닫기 함수
}

// 장비 상세 팝업
function EquipmentModal({ equipment, onClose }: EquipmentModalProps) {
  if (!equipment) return null;

  return (
    <div className="equipment-modal-overlay" onClick={onClose}>
      <div
        className="equipment-modal"
        onClick={(e) => e.stopPropagation()}   // 모달 내부 클릭 시 닫힘 방지
      >
        <div className="equipment-modal-header">
          <div>
            <div className="equipment-modal-title">{equipment.name}</div>
            <div className="equipment-modal-subtitle">
              {equipment.type}
            </div>
          </div>

          <button className="equipment-modal-close" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="equipment-modal-body">
          <div className="equipment-modal-section">
            <div className="equipment-modal-section-title">기본 정보</div>

            <div className="equipment-modal-row">
              <span className="equipment-modal-label">장비 ID</span>
              <span className="equipment-modal-value">{equipment.id}</span>
            </div>

            <div className="equipment-modal-row">
              <span className="equipment-modal-label">상태</span>
              <span className="equipment-modal-value">{equipment.status}</span>
            </div>

            {equipment.currentValue !== undefined && (
              <div className="equipment-modal-row">
                <span className="equipment-modal-label">현재 값</span>
                <span className="equipment-modal-value">
                  {equipment.currentValue}
                  {equipment.unit ? ` ${equipment.unit}` : ""}
                </span>
              </div>
            )}
          </div>

          {equipment.additionalInfo && (
            <div className="equipment-modal-section">
              <div className="equipment-modal-section-title">상세 정보</div>

              {Object.entries(equipment.additionalInfo).map(([key, value]) => (
                <div className="equipment-modal-row" key={key}>
                  <span className="equipment-modal-label">{key}</span>
                  <span className="equipment-modal-value">{value}</span>
                </div>
              ))}
            </div>
          )}

          {equipment.history && equipment.history.length > 0 && (
            <div className="equipment-modal-section">
              <div className="equipment-modal-section-title">최근 히스토리</div>

              <div className="equipment-history-list">
                {equipment.history.map((item, index) => (
                  <div className="equipment-history-row" key={index}>
                    <span className="equipment-history-time">{item.time}</span>
                    <span className="equipment-history-value">
                      {item.value}
                      {equipment.unit ? ` ${equipment.unit}` : ""}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default EquipmentModal;