import { useState } from 'react';
import { StatusBar } from './components/StatusBar';
import { FacilityDiagram } from './components/FacilityDiagram';
import { EquipmentModal } from './components/EquipmentModal';
import { MetricsCards } from './components/MetricsCards';
import type { Equipment } from './components/DetailPanel';

export default function App() {
  const [selectedEquipment, setSelectedEquipment] = useState<Equipment | null>(null);
  const [systemStatus] = useState<'normal' | 'warning' | 'error'>('normal');
  const [alarmCount] = useState(0);

  return (
    <div className="h-screen w-full bg-slate-900 flex flex-col overflow-hidden">
      {/* <StatusBar systemStatus={systemStatus} alarmCount={alarmCount} /> */}
      <div className="flex-1 w-[60%]">
          <FacilityDiagram onEquipmentSelect={setSelectedEquipment} />
      </div>
      {/* <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 w-[80%]">
          <FacilityDiagram onEquipmentSelect={setSelectedEquipment} />
        </div>
        <div className="w-[20%]">
          <MetricsCards />
        </div>
      </div> */}

      <EquipmentModal 
        equipment={selectedEquipment} 
        onClose={() => setSelectedEquipment(null)}
      />
    </div>
  );
}