

window.Globalizer=
{
    GetString:
    function(key)
    {
        if (this[key])
        {
            return this[key];
        }
        
        return ("*MISSING[" + key + "]*");
    },
    GetStringForCount:
    function(key, count)
    {
        if (count == 1)
        {
            return this.GetString(key + "_SINGULAR");
        }

        return this.GetString(key);
    }
,TXT_OK:"OK"}; //;Globalizer.GetString=Globalizer.GetGlobalizedString