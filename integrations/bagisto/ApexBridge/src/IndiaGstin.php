<?php
namespace ApexBooks\Bridge;
final class IndiaGstin
{
    public static function valid(string $value): bool
    {
        if(!preg_match('/^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/D',$value)||!IndiaGstState::resolve(substr($value,0,2)))return false;
        $alphabet='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';$sum=0;
        foreach(str_split(strrev(substr($value,0,14))) as $index=>$char){$product=strpos($alphabet,$char)*($index%2===0?2:1);$sum+=intdiv($product,36)+$product%36;}
        return $value[14]===$alphabet[(36-$sum%36)%36];
    }
}
