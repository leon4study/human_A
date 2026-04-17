import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { ControllerSVG } from '../equipment/ControllerSVG';
import { FilterSVG } from '../equipment/FilterSVG';
import { PumpSVG } from '../equipment/PumpSVG';
import { SprayAnimation } from '../equipment/SprayAnimation';
import { TankSVG } from '../equipment/TankSVG';
import { ValveSVG } from '../equipment/ValveSVG';

type Equipment = {
  id: string;
  name: string;
  type: string;
  status: string;
  currentValue?: number;
  unit?: string;
  history?: { time: string; value: number }[];
  additionalInfo?: Record<string, string>;
};

interface FacilityDiagramProps {
  onEquipmentSelect?: (equipment: Equipment) => void;
}

type PipeTone = 'water' | 'nutrient' | 'steel';

const pipePalette: Record<PipeTone, { shell: string; body: string; flow: string; glow: string }> = {
  water: {
    shell: '#020617',
    body: '#1d4ed8',
    flow: '#60a5fa',
    glow: '#bfdbfe',
  },
  nutrient: {
    shell: '#1c1917',
    body: '#9a3412',
    flow: '#fb923c',
    glow: '#fed7aa',
  },
  steel: {
    shell: '#0f172a',
    body: '#475569',
    flow: '#cbd5e1',
    glow: '#e2e8f0',
  },
};

const nutrientTanks = [
  { id: 'tankA', label: '원액 A', color: '#eab308', x: 70, level: 82 },
  { id: 'tankB', label: '원액 B', color: '#22c55e', x: 75.5, level: 76 },
  { id: 'tankPH', label: 'pH 조절제', color: '#a855f7', x: 81, level: 68 },
  { id: 'tankD', label: '첨가제 D', color: '#94a3b8', x: 86.5, level: 45 },
  { id: 'tankE', label: '첨가제 E', color: '#64748b', x: 92, level: 55 },
] as const;

const valvePositions = [21, 47, 73];
const nutrientTankPipeStartY = 14.4;
const nutrientManifoldY = 20.8;

const growingZones = [
  { left: '15.5%', title: '1구역 딸기 재배지', ph: '6.2', ec: '1.4', accent: '#f472b6' },
  { left: '41.5%', title: '2구역 딸기 재배지', ph: '6.3', ec: '1.5', accent: '#fb7185' },
  { left: '67.5%', title: '3구역 딸기 재배지', ph: '6.1', ec: '1.3', accent: '#f43f5e' },
] as const;

function PipeRun({
  d,
  tone,
  width = 0.8,
  flowWidth = 0.3,
  duration = '1.8s',
  reverseFlow = false,
}: {
  d: string;
  tone: PipeTone;
  width?: number;
  flowWidth?: number;
  duration?: string;
  reverseFlow?: boolean;
}) {
  const palette = pipePalette[tone];

  return (
    <g>
      <path d={d} fill="none" stroke={palette.shell} strokeWidth={width + 0.3} strokeLinecap="round" strokeLinejoin="round" />
      <path d={d} fill="none" stroke={palette.body} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" />
      <path
        d={d}
        fill="none"
        stroke={palette.flow}
        strokeWidth={flowWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray="10 18"
      >
        <animate
          attributeName="stroke-dashoffset"
          from="0"
          to={reverseFlow ? '28' : '-28'}
          dur={duration}
          repeatCount="indefinite"
        />
      </path>
      <path
        d={d}
        fill="none"
        stroke={palette.glow}
        strokeWidth="0.1"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.08"
      />
    </g>
  );
}

function PipeJoint({ x, y, tone = 'steel', size = 0.12 }: { x: number; y: number; tone?: PipeTone; size?: number }) {
  const palette = pipePalette[tone];

  return (
    <g>
      <circle cx={x} cy={y} r={size + 0.08} fill={palette.shell} />
      <circle cx={x} cy={y} r={size} fill={palette.body} stroke="#94a3b8" strokeWidth="0.1" />
      <circle cx={x - 0.08} cy={y - 0.08} r={size * 0.35} fill={palette.glow} opacity="0.45" />
    </g>
  );
}

function FacilityDiagram({ onEquipmentSelect }: FacilityDiagramProps) {
  const [sensorData, setSensorData] = useState({
    waterLevel: 75,
    ph: 6.2,
    ec: 1.5,
    temperature: 22,
    pressure: 2.5,
  });

  const [equipmentStatus] = useState({
    rawWaterPump: true,
    valves: [true, true, true],
  });

  useEffect(() => {
    const interval = setInterval(() => {
      setSensorData((prev) => ({
        waterLevel: Math.min(100, Math.max(0, prev.waterLevel + (Math.random() - 0.5) * 2)),
        ph: Math.max(5.5, Math.min(7.5, prev.ph + (Math.random() - 0.5) * 0.1)),
        ec: Math.max(1.0, Math.min(2.5, prev.ec + (Math.random() - 0.5) * 0.05)),
        temperature: Math.max(18, Math.min(28, prev.temperature + (Math.random() - 0.5) * 0.3)),
        pressure: Math.max(1.5, Math.min(3.5, prev.pressure + (Math.random() - 0.5) * 0.1)),
      }));
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  const generateHistory = (baseValue: number, variation: number) =>
    Array.from({ length: 10 }, (_, i) => ({
      time: `${10 - i}분 전`,
      value: Number((baseValue + (Math.random() - 0.5) * variation).toFixed(2)),
    }));

  const handleEquipmentClick = (
    id: string,
    name: string,
    type: string,
    currentValue?: number,
    unit?: string,
  ) => {
    const equipment: Equipment = {
      id,
      name,
      type,
      status: 'normal',
      currentValue,
      unit,
      history: currentValue ? generateHistory(currentValue, currentValue * 0.1) : undefined,
      additionalInfo:
        id === 'rawWaterTank'
          ? {
              용량: '5000 L',
              경보수위: '20%',
              현재수량: `${((5000 * sensorData.waterLevel) / 100).toFixed(0)} L`,
            }
          : id === 'rawWaterPump'
            ? {
                전류: '12.5 A',
                전압: '220 V',
                가동시간: '142 시간',
                효율: '94%',
              }
            : id === 'autoSupply'
              ? {
                  'pH 제어': '자동',
                  'EC 제어': '자동',
                  가동모드: '연속',
                }
              : undefined,
    };

    if (onEquipmentSelect) {
      onEquipmentSelect(equipment);
    }
  };

  return (
    <div className="relative h-full overflow-hidden bg-slate-900" style={{position: "unset"}}>
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="relative flex h-full w-full max-w-[1500px] flex-col justify-center px-8 py-6">
          <svg
            className="pointer-events-none absolute inset-0 h-full w-full"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            style={{ zIndex: 0 }}
          >
            <defs>
              <radialGradient id="manifoldGlow">
                <stop offset="0%" stopColor="#fb923c" stopOpacity="0.55" />
                <stop offset="100%" stopColor="#fb923c" stopOpacity="0" />
              </radialGradient>
              <radialGradient id="junctionGlow">
                <stop offset="0%" stopColor="#93c5fd" stopOpacity="0.55" />
                <stop offset="100%" stopColor="#93c5fd" stopOpacity="0" />
              </radialGradient>
            </defs>

            <circle cx="55.2" cy="54.6" r="0.32" fill="url(#manifoldGlow)" />
            <circle cx="41.3" cy="17.8" r="0.23" fill="url(#junctionGlow)" />

            <PipeRun d="M 10.8 17.8 H 20" tone="water" width={0.6} flowWidth={0.22} />
            <PipeRun d="M 21 17.8 H 40" tone="water" width={0.6} flowWidth={0.22} />
            <PipeRun d="M 40 17.8 H 54" tone="water" width={0.6} flowWidth={0.22} />

            <PipeRun
              d={`M 59.4 17.8 V ${nutrientManifoldY} H 94.3`}
              tone="steel"
              width={0.5}
              flowWidth={0.18}
              duration="2.2s"
              reverseFlow
            />

            {nutrientTanks.map((tank) => (
              <PipeRun
                key={tank.id}
                d={`M ${tank.x + 2.15} ${nutrientTankPipeStartY} V ${nutrientManifoldY}`}
                tone="steel"
                width={0.36}
                flowWidth={0.13}
                duration="2.4s"
                reverseFlow
              />
            ))}

            <PipeRun d="M 55.5 20 V 55" tone="nutrient" width={0.7} flowWidth={0.26} duration="1.6s" />
            <PipeRun d="M 22 55 H 72" tone="nutrient" width={0.9} flowWidth={0.34} duration="1.9s" />

            {[17, 21, 39, 43.8, 50.8, 55.2].map((x) => (
              <PipeJoint key={`joint-${x}`} x={x} y={17.8} tone="water" />
            ))}
            <PipeJoint x={59.4} y={17.8} tone="steel" size={0.12} />
            <PipeJoint x={59.4} y={nutrientManifoldY} tone="steel" size={0.12} />
            {nutrientTanks.map((tank) => (
              <PipeJoint key={`nutrient-manifold-${tank.id}`} x={tank.x + 2.15} y={nutrientManifoldY} tone="steel" size={0.12} />
            ))}
            <PipeJoint x={94.3} y={nutrientManifoldY} tone="steel" size={0.12} />
            <PipeJoint x={55.2} y={55} tone="nutrient" size={0.13} />
          </svg>

          <div className="relative h-full w-full" style={{ zIndex: 10 }}>
            <motion.div
              className="absolute cursor-pointer"
              style={{ left: '3%', top: '1%' }}
              whileHover={{ scale: 1.05 }}
              onClick={() => handleEquipmentClick('rawWaterTank', '원수 탱크', '저장탱크', sensorData.waterLevel, '%')}
            >
              <TankSVG fillLevel={sensorData.waterLevel} color="#3b82f6" label="rawWater" width={110} height={140} />
              <div className="mt-1 text-center">
                <div className="text-sm font-bold text-white">원수 탱크</div>
              </div>
            </motion.div>

            <motion.div
              className="absolute cursor-pointer"
              style={{ left: '18%', top: '8.5%' }}
              whileHover={{ scale: 1.05 }}
              onClick={() => handleEquipmentClick('filter', '필터', '여과장치')}
            >
              <FilterSVG width={70} height={100} />
              <div className="mt-1 text-center">
                <div className="text-sm font-bold text-white">필터</div>
              </div>
            </motion.div>

            <motion.div
              className="absolute cursor-pointer"
              style={{ left: '35.5%', top: '10%' }}
              whileHover={{ scale: 1.05 }}
              onClick={() => handleEquipmentClick('rawWaterPump', '원수 펌프', '펌프')}
            >
              <PumpSVG isActive={equipmentStatus.rawWaterPump} width={80} height={80} />
              <div className="mt-1 text-center">
                <div className="text-sm font-bold text-white">원수 펌프</div>
                <div className={`text-xs ${equipmentStatus.rawWaterPump ? 'text-green-400' : 'text-gray-400'}`}>
                  {equipmentStatus.rawWaterPump ? 'ON' : 'OFF'}
                </div>
              </div>
            </motion.div>

            <motion.div
              className="absolute cursor-pointer"
              style={{ left: '51%', top: '7.5%' }}
              whileHover={{ scale: 1.05 }}
              onClick={() => handleEquipmentClick('autoSupply', '양액 자동공급기', '자동공급장치')}
            >
              <ControllerSVG width={120} height={150} />
              <div className="mt-1 text-center">
                <div className="text-sm font-bold text-white">양액 자동공급기</div>
              </div>
            </motion.div>

            {nutrientTanks.map((tank) => (
              <motion.div
                key={tank.id}
                className="absolute cursor-pointer"
                style={{ left: `${tank.x}%`, top: '2%' }}
                whileHover={{ scale: 1.05 }}
                onClick={() => handleEquipmentClick(tank.id, tank.label, '약액탱크', tank.level, '%')}
              >
                <TankSVG fillLevel={tank.level} color={tank.color} label={tank.id} width={65} height={80} />
                <div className="mt-1 text-center">
                  <div className="text-[10px] font-bold text-white">{tank.label}</div>
                </div>
              </motion.div>
            ))}

            {equipmentStatus.valves.map((isOpen, i) => (
              <motion.div
                key={`valve-${i}`}
                className="absolute cursor-pointer"
                style={{
                  left: `${[19.45, 45.45, 71.45][i]}%`,
                  top: '52%',
                  zIndex: 30,
                }}
                whileHover={{ scale: 1.2 }}
                onClick={() => handleEquipmentClick(`valve${i + 1}`, `밸브 ${i + 1}`, '분기밸브')}
              >
                <ValveSVG isOpen={isOpen} size={35} />
                <div className="mt-0.5 text-center">
                  <div className="text-[11px] font-bold text-slate-300">V{i + 1}</div>
                </div>
              </motion.div>
            ))}

            <svg
              className="pointer-events-none absolute inset-0 h-full w-full"
              viewBox="0 0 100 100"
              preserveAspectRatio="none"
              style={{ zIndex: 28 }}
            >
              {valvePositions.map((x) => (
                <PipeRun
                  key={`branch-overlay-${x}`}
                  d={`M ${x} 55 V 57.8 Q ${x} 59 ${x - 0.4} 60.2 V 90`}
                  tone="nutrient"
                  width={0.6}
                  flowWidth={0.22}
                  duration="1.5s"
                />
              ))}
              {valvePositions.map((x) => (
                <PipeJoint key={`valve-joint-overlay-${x}`} x={x} y={55} tone="nutrient" size={0.125} />
              ))}
            </svg>

            <svg
              className="pointer-events-none absolute inset-0 h-full w-full"
              viewBox="0 0 100 100"
              preserveAspectRatio="none"
              style={{ zIndex: 29 }}
            >
              {equipmentStatus.valves.map((isOpen, i) => (
                <SprayAnimation key={i} x={valvePositions[i]} y={65} isActive={isOpen} />
              ))}
            </svg>

            {growingZones.map((zone) => (
              <div
                key={zone.title}
                className="absolute h-[34%] w-[10%]"
                style={{ left: zone.left, top: '63%', zIndex: 0 }}
              >
                <div className="relative h-full w-full overflow-hidden rounded-[2rem] border border-emerald-200/10 bg-gradient-to-b from-emerald-950/40 via-emerald-900/25 to-amber-950/70 shadow-[0_20px_45px_rgba(0,0,0,0.28)]">
                  <div className="absolute inset-x-[7%] top-[12%] h-[18%] rounded-full bg-emerald-300/10 blur-md" />
                  <div className="absolute inset-x-[7%] bottom-[6%] top-[6%] rounded-[1.7rem] bg-gradient-to-b from-[#6f4e37] via-[#5a3d2b] to-[#342014]" />

                  {[0, 1].map((column) => (
                    <div
                      key={column}
                      className="absolute top-[16%] bottom-[10%] w-[28%] rounded-[2rem] border border-amber-800/40 bg-gradient-to-b from-[#4a2d1d] via-[#70492f] to-[#4a2d1d] shadow-[inset_0_2px_10px_rgba(255,255,255,0.08)]"
                      style={{ left: `${20 + column * 32}%` }}
                    >
                      <div className="absolute inset-y-[4%] left-[28%] w-[14%] rounded-full bg-black/20" />
                      <div className="absolute inset-y-[4%] right-[28%] w-[14%] rounded-full bg-black/10" />
                      {[0, 1, 2, 3, 4].map((crop) => (
                        <div
                          key={crop}
                          className="absolute left-1/2 h-[14%] w-[55%] -translate-x-1/2"
                          style={{ top: `${8 + crop * 18}%` }}
                        >
                          <div
                            className="absolute left-1/2 top-[34%] h-[58%] w-[8%] -translate-x-1/2 rounded-full bg-emerald-200/80"
                            style={{ boxShadow: `0 0 8px ${zone.accent}30` }}
                          />
                          <div
                            className="absolute left-[14%] top-[2%] h-[42%] w-[44%] -rotate-35 rounded-full bg-gradient-to-br from-emerald-200 to-emerald-500"
                            style={{ border: `1px solid ${zone.accent}66` }}
                          />
                          <div
                            className="absolute right-[14%] top-[4%] h-[40%] w-[42%] rotate-35 rounded-full bg-gradient-to-br from-emerald-100 to-emerald-400"
                            style={{ border: `1px solid ${zone.accent}55` }}
                          />
                          <div
                            className="absolute left-[34%] top-0 h-[18%] w-[28%] rounded-full"
                            style={{ backgroundColor: zone.accent, opacity: 0.9 }}
                          />
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default FacilityDiagram;