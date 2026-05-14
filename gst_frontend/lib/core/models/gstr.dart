import 'package:json_annotation/json_annotation.dart';

part 'gstr.g.dart';

@JsonSerializable()
class Gstr1Bucket {
  final int count;
  final double taxable;
  final double tax;
  final double total;

  const Gstr1Bucket({
    this.count = 0,
    this.taxable = 0,
    this.tax = 0,
    this.total = 0,
  });

  factory Gstr1Bucket.fromJson(Map<String, dynamic> json) {
    final val = json is Map ? json : {};
    return Gstr1Bucket(
      count: val['count'] is int ? val['count'] as int : 0,
      taxable: (val['taxable'] is num ? val['taxable'] : 0).toDouble(),
      tax: (val['tax'] is num ? val['tax'] : 0).toDouble(),
      total: (val['total'] is num ? val['total'] : 0).toDouble(),
    );
  }

  Map<String, dynamic> toJson() => _$Gstr1BucketToJson(this);
}

@JsonSerializable()
class Gstr3bSummary {
  final Gstr3bSection supDetails;
  final Gstr3bSection itcElg;

  const Gstr3bSummary({
    required this.supDetails,
    required this.itcElg,
  });

  factory Gstr3bSummary.fromJson(Map<String, dynamic> json) {
    final data = json is Map ? json : {};
    return Gstr3bSummary(
      supDetails: Gstr3bSection.fromJson(data['sup_details'] ?? {}),
      itcElg: Gstr3bSection.fromJson(data['itc_elg'] ?? {}),
    );
  }

  Map<String, dynamic> toJson() => _$Gstr3bSummaryToJson(this);
}

@JsonSerializable()
class Gstr3bSection {
  final double txval;
  final double iamt;
  final double camt;
  final double samt;
  final double csamt;

  const Gstr3bSection({
    this.txval = 0,
    this.iamt = 0,
    this.camt = 0,
    this.samt = 0,
    this.csamt = 0,
  });

  factory Gstr3bSection.fromJson(Map<String, dynamic> json) {
    final data = json is Map ? json : {};
    double val(String key) =>
        data[key] is num ? (data[key] as num).toDouble() : 0;
    return Gstr3bSection(
      txval: val('txval'),
      iamt: val('iamt'),
      camt: val('camt'),
      samt: val('samt'),
      csamt: val('csamt'),
    );
  }

  Map<String, dynamic> toJson() => _$Gstr3bSectionToJson(this);

  double get totalTax => iamt + camt + samt + csamt;
}