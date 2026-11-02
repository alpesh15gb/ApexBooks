<?php
namespace ApexBooks\Bridge;

/** GSTN place-of-supply master plus Bagisto/ISO regional aliases. */
final class IndiaGstState
{
    public static function resolve(string $state, array $overrides = [], ?string $issued = null): ?string
    {
        static $master = null;
        $master ??= json_decode(file_get_contents(dirname(__DIR__).'/resources/india-gst-states.json'), true, 512, JSON_THROW_ON_ERROR)['states'];
        if (isset($overrides[$state])) return isset($master[(string)$overrides[$state]]) ? (string)$overrides[$state] : null;
        $key = preg_replace('/[^A-Z0-9]/', '', str_replace('&', 'AND', strtoupper(trim($state))));
        if (isset($master[$key])) return $key;
        $aliases = ['AN'=>'35','AP'=>'37','AR'=>'12','AS'=>'18','BR'=>'10','CH'=>'04','CG'=>'22','CT'=>'22','DN'=>'26','DD'=>'26','DL'=>'07','GA'=>'30','GJ'=>'24','HR'=>'06','HP'=>'02','JK'=>'01','JH'=>'20','KA'=>'29','KL'=>'32','LD'=>'31','LA'=>'38','MP'=>'23','MH'=>'27','MN'=>'14','ML'=>'17','MZ'=>'15','NL'=>'13','OD'=>'21','OR'=>'21','PY'=>'34','PB'=>'03','RJ'=>'08','SK'=>'11','TN'=>'33','TG'=>'36','TS'=>'36','TR'=>'16','UP'=>'09','UK'=>'05','UT'=>'05','WB'=>'19',
            'DADRAANDNAGARHAVELI'=>'26','DAMANANDDIU'=>'26','LAKSHADWEEP'=>'31','ORISSA'=>'21','PONDICHERRY'=>'34','UTTARANCHAL'=>'05','NCTOFDELHI'=>'07'];
        if (in_array($key, ['DD','DAMANANDDIU'], true) && $issued && $issued < '2020-01-26') return '25';
        if (isset($aliases[$key])) return $aliases[$key];
        foreach ($master as $code => $name) {
            $normal = preg_replace('/[^A-Z0-9]/', '', str_replace('&', 'AND', strtoupper($name)));
            if ($key === $normal) return str_pad((string)$code,2,'0',STR_PAD_LEFT);
        }
        return null;
    }
}
