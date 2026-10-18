"""제공된 확정 기준만으로 PPC 면적·SKU·수요를 재계산한다. Python 3 표준 라이브러리."""
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR, getcontext
from pathlib import Path
import json
import csv

getcontext().prec = 40
D = Decimal
BASE_AREA = D('463')
ZONES = {'상온': D('65'), '냉장': D('100'), '냉동': D('109'), '입고검수': D('22'),
         '입고창고': D('55'), '패킹': D('24'), '공용통로': D('55')}
TEMPERATURES = ('상온', '냉장', '냉동')
WEIGHTS = (D('.5'), D('.3'), D('.2'))
BRANCHES = [('동래점', '624.9', 182360), ('해운대점', '550', 82010),
            ('사하점', '217.6', 129427), ('남구점', '403.7', 139763),
            ('부산진구점', '332', 205889)]
SCENARIOS = {'보수': (D('.02'), D('1.5')), '기준': (D('.04'), D('2')),
             '낙관': (D('.07'), D('2.5'))}


def rounded(value, digits='0.01'):
    return value.quantize(D(digits), rounding=ROUND_HALF_UP)


def largest_remainder(total):
    raw = [D(total) * w for w in WEIGHTS]
    ints = [int(x.to_integral_value(rounding=ROUND_FLOOR)) for x in raw]
    order = sorted(range(3), key=lambda i: (-(raw[i] - ints[i]), i))
    for i in order[:total - sum(ints)]:
        ints[i] += 1
    return dict(zip(TEMPERATURES, ints))


def calculate():
    results = []
    for name, area_text, households in BRANCHES:
        area = D(area_text)
        ratio = area / BASE_AREA
        raw = {k: v * ratio for k, v in ZONES.items()}
        areas = {k: rounded(v) for k, v in raw.items()}
        unclassified = rounded(area - sum(areas.values()))
        correction = unclassified - rounded(D(33) * ratio)
        areas['배분 미확인 잔여'] = unclassified
        total_sku = int(rounded(D(10900) * ratio, '1'))
        demand = {}
        for scenario, (penetration, frequency) in SCENARIOS.items():
            monthly = D(households) * penetration * frequency
            demand[scenario] = {'monthly_orders': monthly, 'daily_orders': monthly / D(30),
                                'monthly_revenue_krw': monthly * D(30000)}
        results.append({'branch': name, 'area_pyeong': area, 'households': households,
                        'area_multiplier': ratio, 'zone_areas_pyeong': areas,
                        'rounding_adjustment_pyeong': correction,
                        'sku_total': total_sku, 'sku_by_temperature': largest_remainder(total_sku),
                        'demand': demand,
                        'demand_intensity_vs_mokpo': (D(households) / D(75275)) / ratio,
                        'rack_count': None, 'storage_units': None, 'daily_outbound_units': None,
                        'inbound_units': None, 'required_staff': None, 'packing_stations': None,
                        'max_daily_orders': None, 'capacity_status': 'UNKNOWN',
                        'physical_design_status': 'NEEDS_SOURCE'})
    return results


def encode(value):
    if isinstance(value, D):
        return str(value)
    raise TypeError(type(value).__name__)


def write_outputs(output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = calculate()
    payload = {'schema_version': '1.0', 'date': '2026-10-18',
               'scope': '공통 PPC 업무 로직의 제공 수치 기반 계산. 물리 배치 승인 아님.',
               'baseline': {'area_pyeong': '463', 'sku_total': 10900, 'households': 75275,
                            'known_zones_pyeong': ZONES, 'unclassified_remainder_pyeong': '33'},
               'fixed_rack': {'width_mm': 1250, 'depth_mm': 450, 'height_mm': 2100,
                              'shelves': 6, 'shelf_load_limit_kg': 150, 'aisle_mm': 700},
               'rounding': {'method': 'ROUND_HALF_UP', 'zone_decimal_places': 2,
                            'area_correction_target': '배분 미확인 잔여',
                            'sku_distribution': 'largest remainder; ties: 상온, 냉장, 냉동'},
               'conditional_parameters': {'units_per_order': {'candidate': 8, 'status': 'NEEDS_SOURCE'},
                                          'outbound_temperature_weights': {'candidate': ['.5', '.3', '.2'],
                                                                           'status': 'NEEDS_SOURCE'}},
               'missing_inputs': ['목포 원본 MD·이미지', '33평 용도', '온도별 랙 수·배열',
                                  '상품 부피·중량·슬롯·적재율', '박스 입수·팔레트·입고 주기',
                                  '생산성·운영시간·교대·패킹대 규격'],
               'branches': results}
    (output_dir / 'PPC_계산근거.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=encode), encoding='utf-8')
    fields = ['지점', '설계가능면적_평', '가구수', '면적배율'] + [k + '_평' for k in list(ZONES) + ['배분 미확인 잔여']]
    fields += ['면적보정_평', '총SKU', '상온SKU', '냉장SKU', '냉동SKU']
    for scenario in SCENARIOS:
        fields += [scenario + '_월주문', scenario + '_일주문', scenario + '_월매출_원']
    fields += ['목포대비_면적당수요강도', '랙수', '필요인원', '용량판정']
    with (output_dir / 'PPC_지점별_계산표.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(fields)
        for r in results:
            row = [r['branch'], r['area_pyeong'], r['households'], rounded(r['area_multiplier'], '.000001')]
            row += list(r['zone_areas_pyeong'].values())
            row += [r['rounding_adjustment_pyeong'], r['sku_total']] + list(r['sku_by_temperature'].values())
            for scenario in SCENARIOS:
                d = r['demand'][scenario]
                row += [d['monthly_orders'], rounded(d['daily_orders'], '.000001'), d['monthly_revenue_krw']]
            row += [rounded(r['demand_intensity_vs_mokpo'], '.000001'), 'NEEDS_SOURCE', 'NEEDS_SOURCE', 'UNKNOWN']
            writer.writerow(row)
    return results


if __name__ == '__main__':
    write_outputs(Path(__file__).resolve().parent)
    print('PPC_계산근거.json 및 PPC_지점별_계산표.csv 생성 완료')
